"""Pure FotMob team-strength and fixture-context calculation candidate.

Caller-built records are schema candidates, not reviewed evidence. The real
snapshot builder fails closed until a full PR52→PR65 plus reviewed-array adapter
exists. This module does not acquire data, approve arbitrary JSON arrays, adjust
expected goals, build probabilities, accept prices, or authorize anything.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import json
import math
import re
from typing import Any, Iterable


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-team-strength-fixture-intelligence-candidate-v1"
SCOPE = "SCHEMA_ONLY_CANDIDATE_PENDING_FULLY_REVALIDATED_FOTMOB_ARRAY_LINEAGE"
LINEAGE_STATUS = "BLOCKED_MISSING_FULLY_REVALIDATED_FOTMOB_ARRAY_LINEAGE"
SUPPORTED_CONTEXT_STATUS = "SUPPORTED_CONTEXT_NOT_YET_MODEL_FEATURE"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_SAFETY = (
    ("bet_authorized", False),
    ("pricing_authorized", False),
    ("probability_adjustment_authorized", False),
    ("probability_inference_authorized", False),
    ("production_approval_authorized", False),
    ("selection_authorized", False),
    ("team_strength_feature_authorized", False),
)


class TeamStrengthContextError(ValueError):
    pass


class TeamSide(str, enum.Enum):
    HOME = "HOME"
    AWAY = "AWAY"


class PlayerRecordKind(str, enum.Enum):
    STARTER = "STARTER"
    BENCH = "BENCH"
    UNAVAILABLE = "UNAVAILABLE"


class LineupState(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    EXPECTED = "EXPECTED"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    UNVERIFIED_LINEUP_STATE = "UNVERIFIED_LINEUP_STATE"


class PositionGroup(str, enum.Enum):
    GK = "GK"
    DEF = "DEF"
    MID = "MID"
    FWD = "FWD"
    UNKNOWN = "UNKNOWN"


class FeatureStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    BLOCKED = "BLOCKED"


class FeatureBlocker(str, enum.Enum):
    MISSING_BASE_EVIDENCE = "MISSING_BASE_EVIDENCE"
    MISSING_LINEUP = "MISSING_LINEUP"
    UNVERIFIED_LINEUP_STATE = "UNVERIFIED_LINEUP_STATE"
    MISSING_AVAILABILITY_EVIDENCE = "MISSING_AVAILABILITY_EVIDENCE"
    INSUFFICIENT_PRIOR_HISTORY = "INSUFFICIENT_PRIOR_HISTORY"
    MISSING_RATING_SAMPLE = "MISSING_RATING_SAMPLE"
    MISSING_POSITION_EVIDENCE = "MISSING_POSITION_EVIDENCE"
    CONFLICTED_AVAILABILITY_EVIDENCE = "CONFLICTED_AVAILABILITY_EVIDENCE"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    UNVERIFIED_EVIDENCE = "UNVERIFIED_EVIDENCE"


class EvidenceStatus(str, enum.Enum):
    SUPPORTED = "SUPPORTED"
    STALE = "STALE"
    CONFLICTED = "CONFLICTED"
    UNVERIFIED = "UNVERIFIED"


class CompletenessScope(str, enum.Enum):
    CURRENT_AVAILABILITY = "CURRENT_AVAILABILITY"
    SCHEDULE_HISTORY = "SCHEDULE_HISTORY"
    PLAYER_HISTORY = "PLAYER_HISTORY"


class CompletenessDisposition(str, enum.Enum):
    CANDIDATE_ONLY_UNREVIEWED = "CANDIDATE_ONLY_UNREVIEWED"


class BaseStrengthComponentId(str, enum.Enum):
    ELO = "elo"
    FORM = "form"
    ATTACKING_PERFORMANCE = "attacking_performance"
    DEFENSIVE_PERFORMANCE = "defensive_performance"
    HISTORICAL_XG_FOR = "historical_xg_for"
    HISTORICAL_XG_AGAINST = "historical_xg_against"
    VENUE_PERFORMANCE = "venue_performance"


_DERIVED_NAMES = (
    "unavailable_player_count",
    "unavailable_prior_minutes_share_5",
    "unavailable_prior_minutes_share_10",
    "unavailable_prior_start_share_5",
    "unavailable_recent_rating_mass",
    "unavailable_rating_observation_count",
    "xi_recent_rating_mean",
    "xi_minutes_weighted_rating",
    "xi_rating_observation_count",
    "xi_rating_minutes",
    "xi_gk_rating_mean",
    "xi_def_rating_mean",
    "xi_mid_rating_mean",
    "xi_fwd_rating_mean",
    "starters_retained_from_most_recent_match",
    "starter_continuity_previous_5",
    "recent_xi_minutes_retained_share_5",
    "replacement_count",
    "replacement_quality_evidence_gap_count",
    "available_bench_player_count",
    "bench_recent_rating_mean",
    "bench_rating_coverage",
    "rest_days",
    "matches_previous_7_days",
    "matches_previous_14_days",
    "matches_previous_28_days",
)

TeamStrengthFeatureId = enum.Enum(
    "TeamStrengthFeatureId",
    {
        feature_id.upper(): feature_id
        for feature_id in (
            *(f"{side}_base_{component.value}" for side in ("home", "away") for component in BaseStrengthComponentId),
            *(f"{side}_{name}" for side in ("home", "away") for name in _DERIVED_NAMES),
        )
    },
    type=str,
)


def _utc(value: Any, name: str) -> dt.datetime:
    if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise TeamStrengthContextError(f"{name} must be timezone-aware datetime")
    return value.astimezone(dt.timezone.utc)


def _text(value: Any, name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise TeamStrengthContextError(f"{name} must be exact non-empty text")
    return value


def _number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if type(value) not in (int, float):
        raise TeamStrengthContextError(f"{name} must be numeric and not bool")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise TeamStrengthContextError(f"{name} is outside its finite range")
    return result


@dataclasses.dataclass(frozen=True)
class EvidenceAnchor:
    source_reference: str
    observed_at: dt.datetime
    evidence_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_reference", _text(self.source_reference, "source_reference"))
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        if type(self.evidence_sha256) is not str or _SHA.fullmatch(self.evidence_sha256) is None:
            raise TeamStrengthContextError("evidence_sha256 must be lowercase SHA-256")

    def to_dict(self) -> dict[str, Any]:
        return {"source_reference": self.source_reference, "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"), "evidence_sha256": self.evidence_sha256}


@dataclasses.dataclass(frozen=True)
class CompletenessReceiptCandidate:
    provider: str
    source_dataset_name: str
    scope: CompletenessScope
    fixture_identifier: str
    team_id: str
    as_of: dt.datetime
    range_start: dt.datetime
    range_end: dt.datetime
    fixture_ids: tuple[str, ...]
    record_count: int
    evidence: tuple[EvidenceAnchor, ...]
    disposition: CompletenessDisposition = CompletenessDisposition.CANDIDATE_ONLY_UNREVIEWED

    def __post_init__(self) -> None:
        if self.provider != "FOTMOB": raise TeamStrengthContextError("completeness provider must be FOTMOB")
        _text(self.source_dataset_name, "source_dataset_name"); _text(self.fixture_identifier, "fixture_identifier"); _text(self.team_id, "team_id")
        if type(self.scope) is not CompletenessScope or type(self.disposition) is not CompletenessDisposition: raise TeamStrengthContextError("completeness enum drift")
        object.__setattr__(self, "as_of", _utc(self.as_of, "as_of")); object.__setattr__(self, "range_start", _utc(self.range_start, "range_start")); object.__setattr__(self, "range_end", _utc(self.range_end, "range_end"))
        if self.range_start > self.range_end or self.range_end > self.as_of: raise TeamStrengthContextError("completeness range must end by as_of")
        if type(self.fixture_ids) is not tuple or self.fixture_ids != tuple(sorted(set(self.fixture_ids))): raise TeamStrengthContextError("completeness fixture IDs must be unique and sorted")
        for value in self.fixture_ids: _text(value, "fixture_id")
        if type(self.record_count) is not int or self.record_count < 0: raise TeamStrengthContextError("completeness record_count must be nonnegative int")
        if type(self.evidence) is not tuple or not self.evidence or any(type(x) is not EvidenceAnchor for x in self.evidence): raise TeamStrengthContextError("completeness evidence must be nonempty exact tuple")
        if tuple(x.evidence_sha256 for x in self.evidence) != tuple(sorted(set(x.evidence_sha256 for x in self.evidence))): raise TeamStrengthContextError("completeness evidence must be unique and SHA-sorted")
        if any(x.observed_at > self.as_of for x in self.evidence): raise TeamStrengthContextError("completeness evidence observed after as_of")

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "source_dataset_name": self.source_dataset_name, "scope": self.scope.value, "fixture_identifier": self.fixture_identifier, "team_id": self.team_id, "as_of": self.as_of.isoformat().replace("+00:00", "Z"), "range_start": self.range_start.isoformat().replace("+00:00", "Z"), "range_end": self.range_end.isoformat().replace("+00:00", "Z"), "fixture_ids": list(self.fixture_ids), "record_count": self.record_count, "evidence": [x.to_dict() for x in self.evidence], "disposition": self.disposition.value}


@dataclasses.dataclass(frozen=True)
class PlayerRecordCandidate:
    team_id: str
    player_id: str
    kind: PlayerRecordKind
    lineup_state: LineupState
    source_position: str | None
    position_group: PositionGroup
    unavailable_reason: str | None
    evidence: EvidenceAnchor
    availability_conflicted: bool = False
    evidence_status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    valid_through: dt.datetime | None = None

    def __post_init__(self) -> None:
        _text(self.team_id, "team_id"); _text(self.player_id, "player_id")
        if type(self.kind) is not PlayerRecordKind or type(self.lineup_state) is not LineupState or type(self.position_group) is not PositionGroup:
            raise TeamStrengthContextError("player record enum drift")
        if self.source_position is not None: _text(self.source_position, "source_position")
        if self.unavailable_reason is not None: _text(self.unavailable_reason, "unavailable_reason")
        if self.kind is not PlayerRecordKind.UNAVAILABLE and self.unavailable_reason is not None:
            raise TeamStrengthContextError("availability reason is legal only for unavailable player")
        if type(self.evidence) is not EvidenceAnchor:
            raise TeamStrengthContextError("player evidence must be exact EvidenceAnchor")
        if type(self.availability_conflicted) is not bool:
            raise TeamStrengthContextError("availability_conflicted must be exact bool")
        if type(self.evidence_status) is not EvidenceStatus: raise TeamStrengthContextError("player evidence status drift")
        if self.valid_through is not None: object.__setattr__(self, "valid_through", _utc(self.valid_through, "valid_through"))

    def to_dict(self) -> dict[str, Any]:
        return {"team_id": self.team_id, "player_id": self.player_id, "kind": self.kind.value, "lineup_state": self.lineup_state.value, "source_position": self.source_position, "position_group": self.position_group.value, "unavailable_reason": self.unavailable_reason, "availability_conflicted": self.availability_conflicted, "evidence_status": self.evidence_status.value, "valid_through": None if self.valid_through is None else self.valid_through.isoformat().replace("+00:00", "Z"), "evidence": self.evidence.to_dict()}


@dataclasses.dataclass(frozen=True)
class HistoricalPlayerAppearance:
    fixture_identifier: str
    kickoff: dt.datetime
    completed: bool
    team_id: str
    player_id: str
    started: bool
    minutes: float
    rating: float | None
    venue_side: TeamSide
    evidence: EvidenceAnchor
    evidence_status: EvidenceStatus = EvidenceStatus.UNVERIFIED

    def __post_init__(self) -> None:
        _text(self.fixture_identifier, "fixture_identifier"); _text(self.team_id, "team_id"); _text(self.player_id, "player_id")
        object.__setattr__(self, "kickoff", _utc(self.kickoff, "kickoff"))
        if type(self.completed) is not bool or self.completed is not True or type(self.started) is not bool or type(self.venue_side) is not TeamSide:
            raise TeamStrengthContextError("appearance must be completed with exact booleans/venue")
        object.__setattr__(self, "minutes", _number(self.minutes, "minutes", minimum=0.0))
        if self.rating is not None: object.__setattr__(self, "rating", _number(self.rating, "rating", minimum=0.0))
        if type(self.evidence) is not EvidenceAnchor: raise TeamStrengthContextError("appearance evidence drift")
        if type(self.evidence_status) is not EvidenceStatus: raise TeamStrengthContextError("appearance evidence status drift")

    def to_dict(self) -> dict[str, Any]:
        return {"fixture_identifier": self.fixture_identifier, "kickoff": self.kickoff.isoformat().replace("+00:00", "Z"), "completed": self.completed, "team_id": self.team_id, "player_id": self.player_id, "started": self.started, "minutes": self.minutes, "rating": self.rating, "venue_side": self.venue_side.value, "evidence_status": self.evidence_status.value, "evidence": self.evidence.to_dict()}


@dataclasses.dataclass(frozen=True)
class HistoricalTeamFixture:
    fixture_identifier: str
    kickoff: dt.datetime
    completed: bool
    team_ids: tuple[str, str]
    evidence: EvidenceAnchor
    evidence_status: EvidenceStatus = EvidenceStatus.UNVERIFIED

    def __post_init__(self) -> None:
        _text(self.fixture_identifier, "fixture_identifier")
        object.__setattr__(self, "kickoff", _utc(self.kickoff, "kickoff"))
        if self.completed is not True or type(self.team_ids) is not tuple or len(self.team_ids) != 2 or self.team_ids[0] == self.team_ids[1]:
            raise TeamStrengthContextError("historical fixture identity drift")
        for value in self.team_ids: _text(value, "team_id")
        if type(self.evidence) is not EvidenceAnchor: raise TeamStrengthContextError("fixture evidence drift")
        if type(self.evidence_status) is not EvidenceStatus: raise TeamStrengthContextError("fixture evidence status drift")

    def to_dict(self) -> dict[str, Any]:
        return {"fixture_identifier": self.fixture_identifier, "kickoff": self.kickoff.isoformat().replace("+00:00", "Z"), "completed": True, "team_ids": list(self.team_ids), "evidence_status": self.evidence_status.value, "evidence": self.evidence.to_dict()}


@dataclasses.dataclass(frozen=True)
class BaseStrengthComponent:
    team_id: str
    component_id: BaseStrengthComponentId
    value: float | None
    evidence: EvidenceAnchor | None
    evidence_status: EvidenceStatus = EvidenceStatus.UNVERIFIED

    def __post_init__(self) -> None:
        _text(self.team_id, "team_id")
        if type(self.component_id) is not BaseStrengthComponentId: raise TeamStrengthContextError("base component id drift")
        if type(self.evidence_status) is not EvidenceStatus: raise TeamStrengthContextError("base evidence status drift")
        if self.value is None:
            if self.evidence is not None: raise TeamStrengthContextError("missing base value cannot carry evidence")
        else:
            object.__setattr__(self, "value", _number(self.value, "base value"))
            if type(self.evidence) is not EvidenceAnchor: raise TeamStrengthContextError("available base value requires evidence")

    def to_dict(self) -> dict[str, Any]:
        return {"team_id": self.team_id, "component_id": self.component_id.value, "value": self.value, "evidence_status": self.evidence_status.value, "evidence": None if self.evidence is None else self.evidence.to_dict()}


@dataclasses.dataclass(frozen=True)
class SupportedContextRecord:
    context_id: str
    value: Any
    evidence: EvidenceAnchor
    status: str = SUPPORTED_CONTEXT_STATUS
    evidence_status: EvidenceStatus = EvidenceStatus.UNVERIFIED

    def __post_init__(self) -> None:
        _text(self.context_id, "context_id")
        if self.status != SUPPORTED_CONTEXT_STATUS: raise TeamStrengthContextError("context status drift")
        if type(self.evidence) is not EvidenceAnchor: raise TeamStrengthContextError("context evidence drift")
        if type(self.evidence_status) is not EvidenceStatus or self.evidence_status is not EvidenceStatus.SUPPORTED: raise TeamStrengthContextError("supported context requires SUPPORTED evidence status")
        if self.value is None or type(self.value) not in (str, int, float, bool):
            raise TeamStrengthContextError("context value must be an immutable JSON scalar")
        if type(self.value) is float and not math.isfinite(self.value):
            raise TeamStrengthContextError("context value must be finite")

    def to_dict(self) -> dict[str, Any]:
        return {"context_id": self.context_id, "value": self.value, "status": self.status, "evidence_status": self.evidence_status.value, "evidence": self.evidence.to_dict()}


@dataclasses.dataclass(frozen=True)
class TeamStrengthFeatureResolution:
    feature_id: TeamStrengthFeatureId
    status: FeatureStatus
    value: float | None
    blockers: tuple[FeatureBlocker, ...]
    evidence_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.feature_id) is not TeamStrengthFeatureId:
            raise TeamStrengthContextError("feature id must belong to the exact team-strength namespace")
        if type(self.status) is not FeatureStatus or type(self.blockers) is not tuple or any(type(x) is not FeatureBlocker for x in self.blockers): raise TeamStrengthContextError("feature resolution state drift")
        if self.status is FeatureStatus.AVAILABLE:
            object.__setattr__(self, "value", _number(self.value, "feature value"))
            if self.blockers: raise TeamStrengthContextError("available feature cannot carry blockers")
        elif self.value is not None or not self.blockers: raise TeamStrengthContextError("non-available feature must be valueless and blocked")
        if type(self.evidence_sha256s) is not tuple or self.evidence_sha256s != tuple(sorted(set(self.evidence_sha256s))) or any(_SHA.fullmatch(x) is None for x in self.evidence_sha256s): raise TeamStrengthContextError("feature evidence SHA set drift")

    def to_dict(self) -> dict[str, Any]:
        return {"feature_id": self.feature_id.value, "status": self.status.value, "value": self.value, "blockers": [x.value for x in self.blockers], "evidence_sha256s": list(self.evidence_sha256s)}


@dataclasses.dataclass(frozen=True)
class PlayerHistoricalComponent:
    team_id: str
    player_id: str
    source_position: str | None
    position_group: PositionGroup
    status: FeatureStatus
    blockers: tuple[FeatureBlocker, ...]
    starts_previous_5: int | None
    starts_previous_10: int | None
    start_share_previous_5: float | None
    start_share_previous_10: float | None
    contributing_fixture_count_5: int | None
    contributing_fixture_count_10: int | None
    window_coverage_5: float | None
    window_coverage_10: float | None
    minutes_previous_5: float | None
    minutes_previous_10: float | None
    team_minutes_share_5: float | None
    team_minutes_share_10: float | None
    recent_minutes_weighted_rating: float | None
    rating_observation_count: int | None
    rating_minutes: float | None
    recent_xi_participation_count: int | None
    evidence_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.team_id, "team_id"); _text(self.player_id, "player_id")
        if self.source_position is not None: _text(self.source_position, "source_position")
        if type(self.position_group) is not PositionGroup or type(self.status) is not FeatureStatus: raise TeamStrengthContextError("player component enum drift")
        if type(self.blockers) is not tuple or any(type(x) is not FeatureBlocker for x in self.blockers): raise TeamStrengthContextError("player component blocker drift")
        integer_names = ("starts_previous_5", "starts_previous_10", "contributing_fixture_count_5", "contributing_fixture_count_10", "rating_observation_count", "recent_xi_participation_count")
        numeric_names = integer_names + ("start_share_previous_5", "start_share_previous_10", "window_coverage_5", "window_coverage_10", "minutes_previous_5", "minutes_previous_10", "team_minutes_share_5", "team_minutes_share_10", "rating_minutes")
        if self.status is FeatureStatus.AVAILABLE:
            if self.blockers: raise TeamStrengthContextError("available player component cannot carry blockers")
            for name in numeric_names:
                value = getattr(self, name)
                if value is None: raise TeamStrengthContextError(f"available player component requires {name}")
                _number(value, name, minimum=0.0)
            if any(type(getattr(self, name)) is not int for name in integer_names): raise TeamStrengthContextError("player component counts must be exact integers")
            if self.contributing_fixture_count_5 > 5 or self.contributing_fixture_count_10 > 10: raise TeamStrengthContextError("player window counts exceed frozen limits")
            if any(getattr(self, name) > 1.0 for name in ("start_share_previous_5", "start_share_previous_10", "window_coverage_5", "window_coverage_10", "team_minutes_share_5", "team_minutes_share_10")): raise TeamStrengthContextError("player shares must lie in [0,1]")
            if self.recent_minutes_weighted_rating is not None: _number(self.recent_minutes_weighted_rating, "recent_minutes_weighted_rating", minimum=0.0)
        else:
            if not self.blockers: raise TeamStrengthContextError("non-available player component requires blocker")
            if any(getattr(self, name) is not None for name in numeric_names) or self.recent_minutes_weighted_rating is not None: raise TeamStrengthContextError("non-available player component must not contain values")
        if self.status is FeatureStatus.BLOCKED and not set(self.blockers).intersection({FeatureBlocker.CONFLICTED_AVAILABILITY_EVIDENCE, FeatureBlocker.STALE_EVIDENCE, FeatureBlocker.UNVERIFIED_EVIDENCE}): raise TeamStrengthContextError("blocked player component requires upstream evidence blocker")
        if type(self.evidence_sha256s) is not tuple or self.evidence_sha256s != tuple(sorted(set(self.evidence_sha256s))) or any(_SHA.fullmatch(x) is None for x in self.evidence_sha256s): raise TeamStrengthContextError("player component evidence drift")

    def to_dict(self) -> dict[str, Any]:
        return {"team_id": self.team_id, "player_id": self.player_id, "source_position": self.source_position, "position_group": self.position_group.value, "status": self.status.value, "blockers": [x.value for x in self.blockers], "starts_previous_5": self.starts_previous_5, "starts_previous_10": self.starts_previous_10, "start_share_previous_5": self.start_share_previous_5, "start_share_previous_10": self.start_share_previous_10, "contributing_fixture_count_5": self.contributing_fixture_count_5, "contributing_fixture_count_10": self.contributing_fixture_count_10, "window_coverage_5": self.window_coverage_5, "window_coverage_10": self.window_coverage_10, "minutes_previous_5": self.minutes_previous_5, "minutes_previous_10": self.minutes_previous_10, "team_minutes_share_5": self.team_minutes_share_5, "team_minutes_share_10": self.team_minutes_share_10, "recent_minutes_weighted_rating": self.recent_minutes_weighted_rating, "rating_observation_count": self.rating_observation_count, "rating_minutes": self.rating_minutes, "recent_xi_participation_count": self.recent_xi_participation_count, "evidence_sha256s": list(self.evidence_sha256s)}


@dataclasses.dataclass(frozen=True)
class TeamStrengthContextCandidate:
    schema_version: int
    dataset_name: str
    scope: str
    lineage_status: str
    fixture_identifier: str
    home_team_id: str
    away_team_id: str
    kickoff: dt.datetime
    as_of: dt.datetime
    home_lineup_state: LineupState
    away_lineup_state: LineupState
    home_availability_completeness: CompletenessReceiptCandidate | None
    away_availability_completeness: CompletenessReceiptCandidate | None
    home_schedule_history_completeness: CompletenessReceiptCandidate | None
    away_schedule_history_completeness: CompletenessReceiptCandidate | None
    home_player_history_completeness: CompletenessReceiptCandidate | None
    away_player_history_completeness: CompletenessReceiptCandidate | None
    player_components: tuple[PlayerHistoricalComponent, ...]
    features: tuple[TeamStrengthFeatureResolution, ...]
    supported_context: tuple[SupportedContextRecord, ...]
    source_evidence: tuple[EvidenceAnchor, ...]
    source_evidence_sha256s: tuple[str, ...]
    safety: tuple[tuple[str, bool], ...]

    def __post_init__(self) -> None:
        if (self.schema_version, self.dataset_name, self.scope, self.lineage_status) != (SCHEMA_VERSION, DATASET_NAME, SCOPE, LINEAGE_STATUS): raise TeamStrengthContextError("snapshot identity drift")
        _text(self.fixture_identifier, "fixture_identifier"); _text(self.home_team_id, "home_team_id"); _text(self.away_team_id, "away_team_id")
        if self.home_team_id == self.away_team_id: raise TeamStrengthContextError("fixture teams must differ")
        object.__setattr__(self, "kickoff", _utc(self.kickoff, "kickoff")); object.__setattr__(self, "as_of", _utc(self.as_of, "as_of"))
        if self.as_of >= self.kickoff: raise TeamStrengthContextError("snapshot as_of must be before kickoff")
        if type(self.home_lineup_state) is not LineupState or type(self.away_lineup_state) is not LineupState: raise TeamStrengthContextError("lineup state drift")
        completeness = (self.home_availability_completeness, self.away_availability_completeness, self.home_schedule_history_completeness, self.away_schedule_history_completeness, self.home_player_history_completeness, self.away_player_history_completeness)
        if any(value is not None and type(value) is not CompletenessReceiptCandidate for value in completeness): raise TeamStrengthContextError("completeness receipt type drift")
        expected_completeness = ((self.home_availability_completeness, CompletenessScope.CURRENT_AVAILABILITY, self.home_team_id), (self.away_availability_completeness, CompletenessScope.CURRENT_AVAILABILITY, self.away_team_id), (self.home_schedule_history_completeness, CompletenessScope.SCHEDULE_HISTORY, self.home_team_id), (self.away_schedule_history_completeness, CompletenessScope.SCHEDULE_HISTORY, self.away_team_id), (self.home_player_history_completeness, CompletenessScope.PLAYER_HISTORY, self.home_team_id), (self.away_player_history_completeness, CompletenessScope.PLAYER_HISTORY, self.away_team_id))
        if any(receipt is not None and (receipt.scope is not scope or receipt.team_id != team_id or receipt.fixture_identifier != self.fixture_identifier or receipt.as_of != self.as_of) for receipt, scope, team_id in expected_completeness): raise TeamStrengthContextError("completeness receipt scope/fixture/team/as_of drift")
        if type(self.player_components) is not tuple or any(type(x) is not PlayerHistoricalComponent for x in self.player_components): raise TeamStrengthContextError("player components must be exact immutable records")
        if tuple((x.team_id, x.player_id) for x in self.player_components) != tuple(sorted((x.team_id, x.player_id) for x in self.player_components)): raise TeamStrengthContextError("player components must be identity-sorted")
        if len(self.player_components) != len(set((x.team_id, x.player_id) for x in self.player_components)): raise TeamStrengthContextError("duplicate player component identity")
        if type(self.features) is not tuple or any(type(x) is not TeamStrengthFeatureResolution for x in self.features) or tuple(x.feature_id.value for x in self.features) != tuple(sorted(x.feature_id.value for x in self.features)): raise TeamStrengthContextError("features must be exact sorted tuple")
        if {x.feature_id for x in self.features} != set(TeamStrengthFeatureId): raise TeamStrengthContextError("snapshot must resolve the complete team-strength feature namespace")
        if type(self.supported_context) is not tuple or any(type(x) is not SupportedContextRecord for x in self.supported_context) or tuple(x.context_id for x in self.supported_context) != tuple(sorted(x.context_id for x in self.supported_context)): raise TeamStrengthContextError("context records must be sorted")
        if len(self.supported_context) != len(set(x.context_id for x in self.supported_context)): raise TeamStrengthContextError("duplicate supported context identity")
        if type(self.source_evidence) is not tuple or any(type(x) is not EvidenceAnchor for x in self.source_evidence): raise TeamStrengthContextError("source evidence must be exact immutable anchors")
        if tuple(x.evidence_sha256 for x in self.source_evidence) != tuple(sorted(set(x.evidence_sha256 for x in self.source_evidence))): raise TeamStrengthContextError("source evidence anchors must be unique and SHA-sorted")
        if self.source_evidence_sha256s != tuple(x.evidence_sha256 for x in self.source_evidence): raise TeamStrengthContextError("source ancestry drift")
        if any(x.observed_at > self.as_of or x.observed_at >= self.kickoff for x in self.source_evidence): raise TeamStrengthContextError("source ancestry contains post-as_of or post-kickoff evidence")
        ancestry = set(self.source_evidence_sha256s)
        ancestry_records = {x.evidence_sha256: x for x in self.source_evidence}
        if any(not {anchor.evidence_sha256 for anchor in receipt.evidence}.issubset(ancestry) for receipt in completeness if receipt is not None): raise TeamStrengthContextError("completeness evidence is outside snapshot ancestry")
        if any(any(ancestry_records.get(anchor.evidence_sha256) != anchor for anchor in receipt.evidence) for receipt in completeness if receipt is not None): raise TeamStrengthContextError("completeness evidence differs from snapshot ancestry")
        if any(not set(x.evidence_sha256s).issubset(ancestry) for x in self.player_components): raise TeamStrengthContextError("player component references evidence outside snapshot ancestry")
        if any(not set(x.evidence_sha256s).issubset(ancestry) for x in self.features): raise TeamStrengthContextError("feature references evidence outside snapshot ancestry")
        if any(ancestry_records.get(x.evidence.evidence_sha256) != x.evidence for x in self.supported_context): raise TeamStrengthContextError("context evidence differs from snapshot ancestry")
        if self.safety != _SAFETY: raise TeamStrengthContextError("safety authority drift")

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "dataset_name": self.dataset_name, "scope": self.scope, "lineage_status": self.lineage_status, "fixture_identifier": self.fixture_identifier, "home_team_id": self.home_team_id, "away_team_id": self.away_team_id, "kickoff": self.kickoff.isoformat().replace("+00:00", "Z"), "as_of": self.as_of.isoformat().replace("+00:00", "Z"), "home_lineup_state": self.home_lineup_state.value, "away_lineup_state": self.away_lineup_state.value, "home_availability_completeness": None if self.home_availability_completeness is None else self.home_availability_completeness.to_dict(), "away_availability_completeness": None if self.away_availability_completeness is None else self.away_availability_completeness.to_dict(), "home_schedule_history_completeness": None if self.home_schedule_history_completeness is None else self.home_schedule_history_completeness.to_dict(), "away_schedule_history_completeness": None if self.away_schedule_history_completeness is None else self.away_schedule_history_completeness.to_dict(), "home_player_history_completeness": None if self.home_player_history_completeness is None else self.home_player_history_completeness.to_dict(), "away_player_history_completeness": None if self.away_player_history_completeness is None else self.away_player_history_completeness.to_dict(), "home_availability_evidence_present": self.home_availability_evidence_present, "away_availability_evidence_present": self.away_availability_evidence_present, "home_schedule_history_complete": self.home_schedule_history_complete, "away_schedule_history_complete": self.away_schedule_history_complete, "home_player_history_complete": self.home_player_history_complete, "away_player_history_complete": self.away_player_history_complete, "player_components": [x.to_dict() for x in self.player_components], "features": [x.to_dict() for x in self.features], "supported_context": [x.to_dict() for x in self.supported_context], "source_evidence": [x.to_dict() for x in self.source_evidence], "source_evidence_sha256s": list(self.source_evidence_sha256s), "safety": dict(self.safety)}

    @property
    def home_availability_evidence_present(self) -> bool: return self.home_availability_completeness is not None

    @property
    def away_availability_evidence_present(self) -> bool: return self.away_availability_completeness is not None

    @property
    def home_schedule_history_complete(self) -> bool: return self.home_schedule_history_completeness is not None

    @property
    def away_schedule_history_complete(self) -> bool: return self.away_schedule_history_completeness is not None

    @property
    def home_player_history_complete(self) -> bool: return self.home_player_history_completeness is not None

    @property
    def away_player_history_complete(self) -> bool: return self.away_player_history_completeness is not None


def _resolution(feature_id: str, value: float | None, blocker: FeatureBlocker | None, shas: Iterable[str]) -> TeamStrengthFeatureResolution:
    status = FeatureStatus.AVAILABLE if blocker is None else FeatureStatus.BLOCKED if blocker in (FeatureBlocker.UNVERIFIED_LINEUP_STATE, FeatureBlocker.CONFLICTED_AVAILABILITY_EVIDENCE, FeatureBlocker.STALE_EVIDENCE, FeatureBlocker.UNVERIFIED_EVIDENCE) else FeatureStatus.MISSING
    return TeamStrengthFeatureResolution(TeamStrengthFeatureId(feature_id), status, value if blocker is None else None, () if blocker is None else (blocker,), tuple(sorted(set(shas))))


def _evidence_blocker(status: EvidenceStatus) -> FeatureBlocker | None:
    if status is EvidenceStatus.SUPPORTED: return None
    if status is EvidenceStatus.STALE: return FeatureBlocker.STALE_EVIDENCE
    if status is EvidenceStatus.CONFLICTED: return FeatureBlocker.CONFLICTED_AVAILABILITY_EVIDENCE
    return FeatureBlocker.UNVERIFIED_EVIDENCE


def _fixture_window(rows: tuple[HistoricalTeamFixture, ...], team_id: str, count: int) -> tuple[HistoricalTeamFixture, ...]:
    return tuple(sorted((x for x in rows if team_id in x.team_ids), key=lambda x: (x.kickoff, x.fixture_identifier), reverse=True)[:count])


def _appearance_window(rows: tuple[HistoricalPlayerAppearance, ...], fixtures: tuple[HistoricalTeamFixture, ...]) -> tuple[HistoricalPlayerAppearance, ...]:
    fixture_ids = {x.fixture_identifier for x in fixtures}
    return tuple(x for x in rows if x.fixture_identifier in fixture_ids)


def _rating(rows: Iterable[HistoricalPlayerAppearance], player_ids: set[str]) -> tuple[float | None, float | None, int, float, tuple[str, ...]]:
    rated = [x for x in rows if x.player_id in player_ids and x.rating is not None]
    if not rated: return None, None, 0, 0.0, ()
    mean = math.fsum(x.rating for x in rated) / len(rated)
    minutes = math.fsum(x.minutes for x in rated)
    weighted = math.fsum(x.rating * x.minutes for x in rated) / minutes if minutes > 0 else mean
    return mean, weighted, len(rated), minutes, tuple(sorted({x.evidence.evidence_sha256 for x in rated}))


def build_team_strength_context_candidate(*, fixture_identifier: str, home_team_id: str, away_team_id: str, kickoff: dt.datetime, as_of: dt.datetime, home_lineup_state: LineupState, away_lineup_state: LineupState, player_records: tuple[PlayerRecordCandidate, ...], historical_appearances: tuple[HistoricalPlayerAppearance, ...], historical_fixtures: tuple[HistoricalTeamFixture, ...], base_components: tuple[BaseStrengthComponent, ...] = (), supported_context: tuple[SupportedContextRecord, ...] = (), home_availability_completeness: CompletenessReceiptCandidate | None = None, away_availability_completeness: CompletenessReceiptCandidate | None = None, home_schedule_history_completeness: CompletenessReceiptCandidate | None = None, away_schedule_history_completeness: CompletenessReceiptCandidate | None = None, home_player_history_completeness: CompletenessReceiptCandidate | None = None, away_player_history_completeness: CompletenessReceiptCandidate | None = None) -> TeamStrengthContextCandidate:
    _text(fixture_identifier, "fixture_identifier"); _text(home_team_id, "home_team_id"); _text(away_team_id, "away_team_id")
    if home_team_id == away_team_id: raise TeamStrengthContextError("fixture teams must differ")
    if type(home_lineup_state) is not LineupState or type(away_lineup_state) is not LineupState: raise TeamStrengthContextError("lineup states must be exact enums")
    kickoff = _utc(kickoff, "kickoff"); as_of = _utc(as_of, "as_of")
    if as_of >= kickoff: raise TeamStrengthContextError("as_of must be before kickoff")
    exact_tuples = (player_records, historical_appearances, historical_fixtures, base_components, supported_context)
    if any(type(value) is not tuple for value in exact_tuples): raise TeamStrengthContextError("all source record collections must be exact tuples")
    expected_types = (PlayerRecordCandidate, HistoricalPlayerAppearance, HistoricalTeamFixture, BaseStrengthComponent, SupportedContextRecord)
    if any(any(type(item) is not expected for item in values) for values, expected in zip(exact_tuples, expected_types)):
        raise TeamStrengthContextError("source record collection contains wrong record type")
    completeness_receipts = tuple(x for x in (home_availability_completeness, away_availability_completeness, home_schedule_history_completeness, away_schedule_history_completeness, home_player_history_completeness, away_player_history_completeness) if x is not None)
    if any(type(x) is not CompletenessReceiptCandidate for x in completeness_receipts): raise TeamStrengthContextError("completeness inputs must be exact typed receipts")
    completeness_anchors = tuple(anchor for receipt in completeness_receipts for anchor in receipt.evidence)
    source_anchors = tuple([x.evidence for x in player_records] + [x.evidence for x in historical_appearances] + [x.evidence for x in historical_fixtures] + [x.evidence for x in base_components if x.evidence] + [x.evidence for x in supported_context]) + completeness_anchors
    for anchor in source_anchors:
        if anchor.observed_at > as_of or anchor.observed_at >= kickoff: raise TeamStrengthContextError("post-as_of or post-kickoff evidence rejected")
    current_keys = [(x.team_id, x.player_id) for x in player_records]
    if len(current_keys) != len(set(current_keys)): raise TeamStrengthContextError("duplicate/conflicting current player identity")
    appearance_keys = [(x.fixture_identifier, x.team_id, x.player_id) for x in historical_appearances]
    if len(appearance_keys) != len(set(appearance_keys)): raise TeamStrengthContextError("duplicate/conflicting historical player identity")
    fixture_keys = [x.fixture_identifier for x in historical_fixtures]
    if len(fixture_keys) != len(set(fixture_keys)): raise TeamStrengthContextError("duplicate/conflicting historical fixture identity")
    valid_teams = {home_team_id, away_team_id}
    if any(x.team_id not in valid_teams for x in player_records + base_components): raise TeamStrengthContextError("record team outside target fixture")
    expected_states = {home_team_id: home_lineup_state, away_team_id: away_lineup_state}
    if any(x.lineup_state is not expected_states[x.team_id] for x in player_records):
        raise TeamStrengthContextError("player record lineup state conflicts with fixture lineup state")
    if any(state is LineupState.NOT_AVAILABLE and any(x.team_id == team_id and x.kind in (PlayerRecordKind.STARTER, PlayerRecordKind.BENCH) for x in player_records) for team_id, state in expected_states.items()):
        raise TeamStrengthContextError("unavailable lineup cannot contain starter or bench records")
    appearances = tuple(x for x in historical_appearances if x.kickoff < kickoff)
    fixtures = tuple(x for x in historical_fixtures if x.kickoff < kickoff)
    expected_receipts = ((home_availability_completeness, CompletenessScope.CURRENT_AVAILABILITY, home_team_id), (away_availability_completeness, CompletenessScope.CURRENT_AVAILABILITY, away_team_id), (home_schedule_history_completeness, CompletenessScope.SCHEDULE_HISTORY, home_team_id), (away_schedule_history_completeness, CompletenessScope.SCHEDULE_HISTORY, away_team_id), (home_player_history_completeness, CompletenessScope.PLAYER_HISTORY, home_team_id), (away_player_history_completeness, CompletenessScope.PLAYER_HISTORY, away_team_id))
    if any(receipt is not None and (receipt.scope is not scope or receipt.fixture_identifier != fixture_identifier or receipt.team_id != team_id or receipt.as_of != as_of) for receipt, scope, team_id in expected_receipts): raise TeamStrengthContextError("completeness receipt does not bind exact target scope")
    fixture_index = {x.fixture_identifier: x for x in fixtures}
    for appearance in appearances:
        source_fixture = fixture_index.get(appearance.fixture_identifier)
        if source_fixture is None or appearance.kickoff != source_fixture.kickoff or appearance.team_id not in source_fixture.team_ids:
            raise TeamStrengthContextError("historical appearance is not bound to exact fixture identity/time/team")
        expected_venue = TeamSide.HOME if source_fixture.team_ids[0] == appearance.team_id else TeamSide.AWAY
        if appearance.venue_side is not expected_venue:
            raise TeamStrengthContextError("historical appearance venue conflicts with fixture identity")
    feature_rows: list[TeamStrengthFeatureResolution] = []
    player_components: list[PlayerHistoricalComponent] = []
    base_index = {(x.team_id, x.component_id): x for x in base_components}
    if len(base_index) != len(base_components): raise TeamStrengthContextError("duplicate base component")
    for side, team_id, lineup_state, availability_receipt, schedule_receipt, player_history_receipt in (("home", home_team_id, home_lineup_state, home_availability_completeness, home_schedule_history_completeness, home_player_history_completeness), ("away", away_team_id, away_lineup_state, away_availability_completeness, away_schedule_history_completeness, away_player_history_completeness)):
        availability_present = availability_receipt is not None
        schedule_complete = schedule_receipt is not None
        for component_id in BaseStrengthComponentId:
            item = base_index.get((team_id, component_id))
            base_blocker = FeatureBlocker.MISSING_BASE_EVIDENCE if item is None or item.value is None else _evidence_blocker(item.evidence_status)
            feature_rows.append(_resolution(f"{side}_base_{component_id.value}", None if item is None else item.value, base_blocker, () if item is None or item.evidence is None else (item.evidence.evidence_sha256,)))
        current = tuple(x for x in player_records if x.team_id == team_id)
        starters = tuple(x for x in current if x.kind is PlayerRecordKind.STARTER)
        bench = tuple(x for x in current if x.kind is PlayerRecordKind.BENCH)
        unavailable = tuple(x for x in current if x.kind is PlayerRecordKind.UNAVAILABLE)
        if availability_receipt is not None and (availability_receipt.fixture_ids != (fixture_identifier,) or availability_receipt.record_count != len(unavailable)):
            raise TeamStrengthContextError("availability completeness receipt does not bind exact target record set")
        current_status_blockers = tuple(_evidence_blocker(x.evidence_status) for x in current if _evidence_blocker(x.evidence_status) is not None)
        if any(x.valid_through is None or x.valid_through < as_of for x in current): current_status_blockers += (FeatureBlocker.STALE_EVIDENCE,)
        availability_conflicted = any(x.availability_conflicted for x in current)
        if availability_conflicted:
            lineup_blocker = FeatureBlocker.CONFLICTED_AVAILABILITY_EVIDENCE
        elif current_status_blockers:
            lineup_blocker = current_status_blockers[0]
        elif lineup_state is LineupState.UNVERIFIED_LINEUP_STATE:
            lineup_blocker = FeatureBlocker.UNVERIFIED_LINEUP_STATE
        elif lineup_state is LineupState.NOT_AVAILABLE or not starters:
            lineup_blocker = FeatureBlocker.MISSING_LINEUP
        else:
            lineup_blocker = None
        availability_blocker = FeatureBlocker.CONFLICTED_AVAILABILITY_EVIDENCE if availability_conflicted else current_status_blockers[0] if current_status_blockers else None if availability_present else FeatureBlocker.MISSING_AVAILABILITY_EVIDENCE
        team_fixtures_in_range = tuple(x for x in fixtures if team_id in x.team_ids and (schedule_receipt is None or schedule_receipt.range_start <= x.kickoff < schedule_receipt.range_end))
        if schedule_receipt is not None and (schedule_receipt.fixture_ids != tuple(sorted(x.fixture_identifier for x in team_fixtures_in_range)) or schedule_receipt.record_count != len(team_fixtures_in_range)):
            raise TeamStrengthContextError("schedule completeness receipt does not bind exact fixture range")
        player_fixtures_in_range = tuple(x for x in fixtures if team_id in x.team_ids and (player_history_receipt is None or player_history_receipt.range_start <= x.kickoff < player_history_receipt.range_end))
        player_rows_in_range = tuple(x for x in appearances if x.team_id == team_id and x.fixture_identifier in {f.fixture_identifier for f in player_fixtures_in_range})
        if player_history_receipt is not None and (player_history_receipt.fixture_ids != tuple(sorted(x.fixture_identifier for x in player_fixtures_in_range)) or player_history_receipt.record_count != len(player_rows_in_range)):
            raise TeamStrengthContextError("player-history completeness receipt does not bind exact fixture/evidence range")
        history_status_blockers = tuple(_evidence_blocker(x.evidence_status) for x in player_rows_in_range + team_fixtures_in_range if _evidence_blocker(x.evidence_status) is not None)
        player_history_blocker = history_status_blockers[0] if history_status_blockers else None if player_history_receipt is not None and schedule_complete else FeatureBlocker.INSUFFICIENT_PRIOR_HISTORY
        fixture_window5 = _fixture_window(fixtures, team_id, 5); fixture_window10 = _fixture_window(fixtures, team_id, 10)
        window5 = _appearance_window(appearances, fixture_window5); window10 = _appearance_window(appearances, fixture_window10)
        availability_shas = () if availability_receipt is None else tuple(x.evidence_sha256 for x in availability_receipt.evidence)
        sha_current = tuple(x.evidence.evidence_sha256 for x in current) + availability_shas
        sha_window5 = tuple(x.evidence.evidence_sha256 for x in window5)
        sha_window10 = tuple(x.evidence.evidence_sha256 for x in window10)
        player_history_sha = () if player_history_receipt is None else tuple(x.evidence_sha256 for x in player_history_receipt.evidence)
        unavail_ids = {x.player_id for x in unavailable}; starter_ids = {x.player_id for x in starters}; bench_ids = {x.player_id for x in bench}
        total_minutes5 = math.fsum(x.minutes for x in window5); total_minutes10 = math.fsum(x.minutes for x in window10)
        team_match_count5 = len(fixture_window5); team_match_count10 = len(fixture_window10)
        unavail_minutes5 = math.fsum(x.minutes for x in window5 if x.player_id in unavail_ids); unavail_minutes10 = math.fsum(x.minutes for x in window10 if x.player_id in unavail_ids)
        total_starts5 = sum(x.started for x in window5); unavailable_starts5 = sum(x.started for x in window5 if x.player_id in unavail_ids)
        unavail_rated = [x for x in window10 if x.player_id in unavail_ids and x.rating is not None]
        total_rating_mass = math.fsum(x.rating * x.minutes for x in window10 if x.rating is not None)
        unavailable_rating_mass = math.fsum(x.rating * x.minutes for x in unavail_rated)
        for record in current:
            player5 = tuple(x for x in window5 if x.player_id == record.player_id)
            player10 = tuple(x for x in window10 if x.player_id == record.player_id)
            rated = tuple(x for x in player10 if x.rating is not None)
            rating_minutes = math.fsum(x.minutes for x in rated)
            rating_value = math.fsum(x.rating * x.minutes for x in rated) / rating_minutes if rating_minutes else (math.fsum(x.rating for x in rated) / len(rated) if rated else None)
            component_blocker = FeatureBlocker.CONFLICTED_AVAILABILITY_EVIDENCE if record.availability_conflicted else _evidence_blocker(record.evidence_status) or (FeatureBlocker.STALE_EVIDENCE if record.valid_through is None or record.valid_through < as_of else None) or player_history_blocker or (FeatureBlocker.INSUFFICIENT_PRIOR_HISTORY if not fixture_window10 else None)
            component_status = FeatureStatus.BLOCKED if component_blocker in (FeatureBlocker.CONFLICTED_AVAILABILITY_EVIDENCE, FeatureBlocker.STALE_EVIDENCE, FeatureBlocker.UNVERIFIED_EVIDENCE) else FeatureStatus.MISSING if component_blocker else FeatureStatus.AVAILABLE
            values = None if component_blocker else (
                sum(x.started for x in player5),
                sum(x.started for x in player10),
                sum(x.started for x in player5) / team_match_count5,
                sum(x.started for x in player10) / team_match_count10,
                team_match_count5,
                team_match_count10,
                team_match_count5 / 5.0,
                team_match_count10 / 10.0,
                math.fsum(x.minutes for x in player5),
                math.fsum(x.minutes for x in player10),
                math.fsum(x.minutes for x in player5) / total_minutes5 if total_minutes5 else 0.0,
                math.fsum(x.minutes for x in player10) / total_minutes10 if total_minutes10 else 0.0,
                rating_value,
                len(rated),
                rating_minutes,
                sum(x.started for x in player5),
            )
            component_shas = tuple(sorted(set((record.evidence.evidence_sha256,) + player_history_sha + tuple(x.evidence.evidence_sha256 for x in player10))))
            player_components.append(PlayerHistoricalComponent(record.team_id, record.player_id, record.source_position, record.position_group, component_status, () if component_blocker is None else (component_blocker,), *(values if values is not None else (None,) * 16), component_shas))
        feature_rows += [
            _resolution(f"{side}_unavailable_player_count", float(len(unavailable)), availability_blocker, sha_current),
            _resolution(f"{side}_unavailable_prior_minutes_share_5", unavail_minutes5 / total_minutes5 if total_minutes5 else None, availability_blocker or player_history_blocker or (FeatureBlocker.INSUFFICIENT_PRIOR_HISTORY if not total_minutes5 else None), sha_current + player_history_sha + sha_window5),
            _resolution(f"{side}_unavailable_prior_minutes_share_10", unavail_minutes10 / total_minutes10 if total_minutes10 else None, availability_blocker or player_history_blocker or (FeatureBlocker.INSUFFICIENT_PRIOR_HISTORY if not total_minutes10 else None), sha_current + player_history_sha + sha_window10),
            _resolution(f"{side}_unavailable_prior_start_share_5", unavailable_starts5 / total_starts5 if total_starts5 else None, availability_blocker or player_history_blocker or (FeatureBlocker.INSUFFICIENT_PRIOR_HISTORY if not total_starts5 else None), sha_current + player_history_sha + sha_window5),
            _resolution(f"{side}_unavailable_recent_rating_mass", unavailable_rating_mass / total_rating_mass if total_rating_mass else None, availability_blocker or player_history_blocker or (FeatureBlocker.MISSING_RATING_SAMPLE if not total_rating_mass else None), sha_current + player_history_sha + sha_window10),
            _resolution(f"{side}_unavailable_rating_observation_count", float(len(unavail_rated)), availability_blocker or player_history_blocker, sha_current + player_history_sha + sha_window10),
        ]
        mean, weighted, count, minutes, rating_shas = _rating(window10, starter_ids)
        rating_blocker = lineup_blocker or player_history_blocker or (FeatureBlocker.MISSING_RATING_SAMPLE if count == 0 else None)
        feature_rows += [
            _resolution(f"{side}_xi_recent_rating_mean", mean, rating_blocker, sha_current + player_history_sha + rating_shas),
            _resolution(f"{side}_xi_minutes_weighted_rating", weighted, rating_blocker, sha_current + player_history_sha + rating_shas),
            _resolution(f"{side}_xi_rating_observation_count", float(count), lineup_blocker or player_history_blocker, sha_current + player_history_sha + rating_shas),
            _resolution(f"{side}_xi_rating_minutes", minutes, lineup_blocker or player_history_blocker, sha_current + player_history_sha + rating_shas),
        ]
        for group in (PositionGroup.GK, PositionGroup.DEF, PositionGroup.MID, PositionGroup.FWD):
            ids = {x.player_id for x in starters if x.position_group is group}
            group_mean, _, group_count, _, group_shas = _rating(window10, ids)
            blocker = lineup_blocker or player_history_blocker or (FeatureBlocker.MISSING_POSITION_EVIDENCE if not ids else FeatureBlocker.MISSING_RATING_SAMPLE if not group_count else None)
            feature_rows.append(_resolution(f"{side}_xi_{group.value.lower()}_rating_mean", group_mean, blocker, sha_current + player_history_sha + group_shas))
        recent_id = fixture_window5[0].fixture_identifier if fixture_window5 else None
        recent_starters = {x.player_id for x in window5 if x.fixture_identifier == recent_id and x.started}
        retained = len(starter_ids & recent_starters)
        starts_retained = sum(x.started for x in window5 if x.player_id in starter_ids)
        xi_minutes = math.fsum(x.minutes for x in window5 if x.player_id in starter_ids)
        history_blocker = lineup_blocker or player_history_blocker or (FeatureBlocker.INSUFFICIENT_PRIOR_HISTORY if not fixture_window5 else None)
        feature_rows += [
            _resolution(f"{side}_starters_retained_from_most_recent_match", float(retained), history_blocker, sha_current + player_history_sha + sha_window5),
            _resolution(f"{side}_starter_continuity_previous_5", starts_retained / total_starts5 if total_starts5 else None, lineup_blocker or player_history_blocker or (FeatureBlocker.INSUFFICIENT_PRIOR_HISTORY if not total_starts5 else None), sha_current + player_history_sha + sha_window5),
            _resolution(f"{side}_recent_xi_minutes_retained_share_5", xi_minutes / total_minutes5 if total_minutes5 else None, lineup_blocker or player_history_blocker or (FeatureBlocker.INSUFFICIENT_PRIOR_HISTORY if not total_minutes5 else None), sha_current + player_history_sha + sha_window5),
            _resolution(f"{side}_replacement_count", float(len(starter_ids - recent_starters)), history_blocker, sha_current + player_history_sha + sha_window5),
            _resolution(f"{side}_replacement_quality_evidence_gap_count", float(sum(1 for player_id in starter_ids - recent_starters if not any(x.player_id == player_id and x.rating is not None for x in window10))), history_blocker, sha_current + player_history_sha + sha_window10),
        ]
        bench_mean, _, bench_count, _, bench_shas = _rating(window10, bench_ids)
        rated_bench_players = {x.player_id for x in window10 if x.player_id in bench_ids and x.rating is not None}
        feature_rows += [
            _resolution(f"{side}_available_bench_player_count", float(len(bench)), lineup_blocker, sha_current),
            _resolution(f"{side}_bench_recent_rating_mean", bench_mean, lineup_blocker or player_history_blocker or (FeatureBlocker.MISSING_RATING_SAMPLE if not bench_count else None), sha_current + player_history_sha + bench_shas),
            _resolution(f"{side}_bench_rating_coverage", len(rated_bench_players) / len(bench) if bench else None, lineup_blocker or player_history_blocker or (FeatureBlocker.MISSING_LINEUP if not bench else None), sha_current + player_history_sha + bench_shas),
        ]
        team_fixtures = sorted((x for x in fixtures if team_id in x.team_ids), key=lambda x: (x.kickoff, x.fixture_identifier), reverse=True)
        fixture_shas = tuple(x.evidence.evidence_sha256 for x in team_fixtures) + (() if schedule_receipt is None else tuple(x.evidence_sha256 for x in schedule_receipt.evidence))
        feature_rows.append(_resolution(f"{side}_rest_days", (kickoff - team_fixtures[0].kickoff).total_seconds() / 86400.0 if team_fixtures and schedule_complete else None, FeatureBlocker.INSUFFICIENT_PRIOR_HISTORY if not team_fixtures or not schedule_complete else None, fixture_shas))
        for days in (7, 14, 28):
            count_days = sum(1 for x in team_fixtures if kickoff - dt.timedelta(days=days) <= x.kickoff < kickoff)
            feature_rows.append(_resolution(f"{side}_matches_previous_{days}_days", float(count_days) if schedule_complete else None, None if schedule_complete else FeatureBlocker.INSUFFICIENT_PRIOR_HISTORY, fixture_shas))
    material_source_anchors = tuple([x.evidence for x in player_records] + [x.evidence for x in appearances] + [x.evidence for x in fixtures] + [x.evidence for x in base_components if x.evidence] + [x.evidence for x in supported_context]) + completeness_anchors
    material_anchors_by_sha: dict[str, EvidenceAnchor] = {}
    for anchor in material_source_anchors:
        previous = material_anchors_by_sha.get(anchor.evidence_sha256)
        if previous is not None and previous != anchor:
            raise TeamStrengthContextError("one evidence SHA cannot claim conflicting source ancestry")
        material_anchors_by_sha[anchor.evidence_sha256] = anchor
    material_anchors = tuple(material_anchors_by_sha[key] for key in sorted(material_anchors_by_sha))
    all_shas = tuple(x.evidence_sha256 for x in material_anchors)
    return TeamStrengthContextCandidate(SCHEMA_VERSION, DATASET_NAME, SCOPE, LINEAGE_STATUS, fixture_identifier, home_team_id, away_team_id, kickoff, as_of, home_lineup_state, away_lineup_state, home_availability_completeness, away_availability_completeness, home_schedule_history_completeness, away_schedule_history_completeness, home_player_history_completeness, away_player_history_completeness, tuple(sorted(player_components, key=lambda x: (x.team_id, x.player_id))), tuple(sorted(feature_rows, key=lambda x: x.feature_id.value)), tuple(sorted(supported_context, key=lambda x: x.context_id)), material_anchors, all_shas, _SAFETY)


def build_team_strength_context_snapshot(**_: Any) -> TeamStrengthContextCandidate:
    """Fail closed until an exact reviewed FotMob array-lineage adapter exists."""

    raise TeamStrengthContextError(LINEAGE_STATUS)


def canonical_team_strength_context_candidate_bytes(candidate: TeamStrengthContextCandidate) -> bytes:
    if type(candidate) is not TeamStrengthContextCandidate: raise TypeError("candidate must be exact TeamStrengthContextCandidate")
    def rebuild_receipt(value: CompletenessReceiptCandidate | None) -> CompletenessReceiptCandidate | None:
        return None if value is None else dataclasses.replace(value, evidence=tuple(dataclasses.replace(x) for x in value.evidence))
    rebuilt = dataclasses.replace(
        candidate,
        home_availability_completeness=rebuild_receipt(candidate.home_availability_completeness),
        away_availability_completeness=rebuild_receipt(candidate.away_availability_completeness),
        home_schedule_history_completeness=rebuild_receipt(candidate.home_schedule_history_completeness),
        away_schedule_history_completeness=rebuild_receipt(candidate.away_schedule_history_completeness),
        home_player_history_completeness=rebuild_receipt(candidate.home_player_history_completeness),
        away_player_history_completeness=rebuild_receipt(candidate.away_player_history_completeness),
        player_components=tuple(dataclasses.replace(x) for x in candidate.player_components),
        features=tuple(dataclasses.replace(x) for x in candidate.features),
        supported_context=tuple(dataclasses.replace(x, evidence=dataclasses.replace(x.evidence)) for x in candidate.supported_context),
        source_evidence=tuple(dataclasses.replace(x) for x in candidate.source_evidence),
        source_evidence_sha256s=tuple(candidate.source_evidence_sha256s),
        safety=tuple(candidate.safety),
    )
    return (json.dumps(rebuilt.to_dict(), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_team_strength_context_candidate(candidate: TeamStrengthContextCandidate) -> str:
    return hashlib.sha256(canonical_team_strength_context_candidate_bytes(candidate)).hexdigest()


__all__ = [name for name in globals() if name.startswith(("Base", "Completeness", "Evidence", "Feature", "Historical", "Lineup", "Player", "Position", "Supported", "TeamStrength"))] + ["LINEAGE_STATUS", "TeamSide", "build_team_strength_context_candidate", "build_team_strength_context_snapshot", "canonical_team_strength_context_candidate_bytes", "sha256_team_strength_context_candidate"]
