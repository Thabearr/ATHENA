"""Exact PR193 player-context -> PR190 team-strength feature handoff.

This boundary replays the frozen PR192 evidence through PR193, then maps only
semantics actually admitted by PR193 into the PR190 candidate schema. It does
not invent bench, position, historical-player, base-strength, probability,
pricing, selection, or BET authority.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
import types
from typing import Any, Mapping

from domain.fotmob_real_player_context_array_admission import (
    DATASET_NAME as ADMISSION_DATASET_NAME,
    PlayerContextSetScope,
    ReviewedRealFotMobPlayerContextAdmission,
    build_reviewed_real_fotmob_player_context_admission,
    canonical_reviewed_real_fotmob_player_context_admission_bytes,
)
from domain.fotmob_team_strength_fixture_intelligence import (
    CompletenessReceiptCandidate,
    CompletenessScope,
    EvidenceAnchor,
    EvidenceStatus,
    FeatureStatus,
    LineupState,
    PlayerRecordCandidate,
    PlayerRecordKind,
    PositionGroup,
    TeamSide,
    TeamStrengthContextCandidate,
    TeamStrengthContextError,
    build_team_strength_context_candidate,
    canonical_team_strength_context_candidate_bytes,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-real-player-context-team-strength-handoff-v1"
HANDOFF_SCOPE = "EXACT_PR193_OBSERVATION_TEAM_STRENGTH_FEATURE_HANDOFF_ONLY"
_SHA = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

_AUTHORITY = tuple(
    sorted(
        {
            "bet_authorized": False,
            "bench_semantics_used": False,
            "historical_player_evidence_used": False,
            "position_semantics_used": False,
            "pricing_authorized": False,
            "probability_adjustment_authorized": False,
            "probability_inference_authorized": False,
            "production_approval_authorized": False,
            "prospective_reuse_after_source_freshness_authorized": False,
            "selection_authorized": False,
            "team_strength_feature_authorized": True,
        }.items()
    )
)
_EXPECTED_AVAILABLE_FEATURES = {
    "away_unavailable_player_count": 5.0,
    "home_unavailable_player_count": 1.0,
}
_EXPECTED_AVAILABLE_FEATURE_IDS = tuple(sorted(_EXPECTED_AVAILABLE_FEATURES))


class RealPlayerContextTeamStrengthHandoffError(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
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
        raise RealPlayerContextTeamStrengthHandoffError("handoff canonicalization failed") from exc


def _source_identity(prefix: str, value: int | str) -> str:
    if type(prefix) is not str or not prefix or prefix != prefix.strip():
        raise RealPlayerContextTeamStrengthHandoffError("source identity prefix must be exact text")
    if type(value) is int:
        kind = "INTEGER"
    elif type(value) is str and value and value == value.strip():
        kind = "STRING"
    else:
        raise RealPlayerContextTeamStrengthHandoffError(
            "source identity must be exact int/non-empty trimmed string"
        )
    return f"{prefix}:{kind}:{value}"


def _aware_utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise RealPlayerContextTeamStrengthHandoffError(f"{label} must be timezone-aware datetime")
    return value.astimezone(dt.timezone.utc)


def _new(**values: Any) -> "ReviewedRealFotMobTeamStrengthHandoff":
    obj = object.__new__(ReviewedRealFotMobTeamStrengthHandoff)
    expected = {field.name for field in dataclasses.fields(ReviewedRealFotMobTeamStrengthHandoff)}
    if set(values) != expected:
        raise RealPlayerContextTeamStrengthHandoffError("internal handoff field drift")
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    obj.__post_init__()
    return obj


@dataclasses.dataclass(frozen=True, init=False)
class ReviewedRealFotMobTeamStrengthHandoff:
    schema_version: int
    dataset_name: str
    handoff_scope: str
    source_admission_sha256: str
    source_admission_size: int
    source_raw_sha256: str
    fixture_identifier: str
    source_match_id: str
    home_team_id: str
    away_team_id: str
    source_observed_at: dt.datetime
    source_classified_at: dt.datetime
    source_state_fresh_until: dt.datetime
    candidate: TeamStrengthContextCandidate
    candidate_sha256: str
    candidate_size: int
    available_feature_ids: tuple[str, ...]
    missing_feature_count: int
    blocked_feature_count: int
    authority: Mapping[str, bool]

    def __init__(self, *_: Any, **__: Any) -> None:
        raise RealPlayerContextTeamStrengthHandoffError(
            "authoritative handoff only from exact PR193 source replay"
        )

    def __post_init__(self) -> None:
        if (self.schema_version, self.dataset_name, self.handoff_scope) != (
            SCHEMA_VERSION,
            DATASET_NAME,
            HANDOFF_SCOPE,
        ):
            raise RealPlayerContextTeamStrengthHandoffError("handoff identity drift")
        if type(self.source_admission_sha256) is not str or _SHA.fullmatch(self.source_admission_sha256) is None:
            raise RealPlayerContextTeamStrengthHandoffError("source admission SHA drift")
        if type(self.source_raw_sha256) is not str or _SHA.fullmatch(self.source_raw_sha256) is None:
            raise RealPlayerContextTeamStrengthHandoffError("source raw SHA drift")
        if type(self.source_admission_size) is not int or self.source_admission_size <= 0:
            raise RealPlayerContextTeamStrengthHandoffError("source admission size drift")
        if type(self.fixture_identifier) is not str or not self.fixture_identifier:
            raise RealPlayerContextTeamStrengthHandoffError("fixture identity drift")
        if type(self.source_match_id) is not str or not self.source_match_id:
            raise RealPlayerContextTeamStrengthHandoffError("source match identity drift")
        if (
            type(self.home_team_id) is not str
            or type(self.away_team_id) is not str
            or not self.home_team_id
            or not self.away_team_id
            or self.home_team_id == self.away_team_id
        ):
            raise RealPlayerContextTeamStrengthHandoffError("team identity drift")
        observed = _aware_utc(self.source_observed_at, "source_observed_at")
        classified = _aware_utc(self.source_classified_at, "source_classified_at")
        fresh_until = _aware_utc(self.source_state_fresh_until, "source_state_fresh_until")
        if observed >= classified:
            raise RealPlayerContextTeamStrengthHandoffError("source observation must precede classification")
        if type(self.candidate) is not TeamStrengthContextCandidate:
            raise RealPlayerContextTeamStrengthHandoffError("nested value must be exact PR190 candidate")
        if classified >= self.candidate.kickoff:
            raise RealPlayerContextTeamStrengthHandoffError("classification must remain prospective")
        candidate_bytes = canonical_team_strength_context_candidate_bytes(self.candidate)
        if self.candidate_sha256 != _sha(candidate_bytes) or self.candidate_size != len(candidate_bytes):
            raise RealPlayerContextTeamStrengthHandoffError("nested candidate canonical identity drift")
        if (
            self.candidate.fixture_identifier,
            self.candidate.home_team_id,
            self.candidate.away_team_id,
            self.candidate.as_of,
        ) != (
            self.fixture_identifier,
            self.home_team_id,
            self.away_team_id,
            classified,
        ):
            raise RealPlayerContextTeamStrengthHandoffError("nested fixture/team/as-of identity drift")
        if (
            self.candidate.home_lineup_state is not LineupState.UNVERIFIED_LINEUP_STATE
            or self.candidate.away_lineup_state is not LineupState.UNVERIFIED_LINEUP_STATE
        ):
            raise RealPlayerContextTeamStrengthHandoffError(
                "missing bench must keep aggregate lineup state unverified"
            )
        if any(value for _, value in self.candidate.safety):
            raise RealPlayerContextTeamStrengthHandoffError(
                "nested PR190 candidate safety must remain all false"
            )
        available_rows = {
            item.feature_id.value: item.value
            for item in self.candidate.features
            if item.status is FeatureStatus.AVAILABLE
        }
        available = tuple(sorted(available_rows))
        missing = sum(item.status is FeatureStatus.MISSING for item in self.candidate.features)
        blocked = sum(item.status is FeatureStatus.BLOCKED for item in self.candidate.features)
        if available_rows != _EXPECTED_AVAILABLE_FEATURES or self.available_feature_ids != available:
            raise RealPlayerContextTeamStrengthHandoffError(
                "available feature set exceeds exact admitted semantics"
            )
        if self.missing_feature_count != missing or self.blocked_feature_count != blocked:
            raise RealPlayerContextTeamStrengthHandoffError("feature status counts drift")
        if any(
            item.source_position is not None or item.position_group is not PositionGroup.UNKNOWN
            for item in self.candidate.player_components
        ):
            raise RealPlayerContextTeamStrengthHandoffError(
                "position semantics leaked into team-strength candidate"
            )
        if any(item.status is FeatureStatus.AVAILABLE for item in self.candidate.player_components):
            raise RealPlayerContextTeamStrengthHandoffError(
                "historical player features require reviewed history"
            )
        if fresh_until != classified:
            raise RealPlayerContextTeamStrengthHandoffError(
                "source freshness must not project beyond PR193 classification"
            )
        if tuple(self.authority.items()) != _AUTHORITY:
            raise RealPlayerContextTeamStrengthHandoffError("handoff authority drift")

    def to_dict(self) -> dict[str, Any]:
        iso = lambda value: value.isoformat().replace("+00:00", "Z")
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "handoff_scope": self.handoff_scope,
            "source_admission_sha256": self.source_admission_sha256,
            "source_admission_size": self.source_admission_size,
            "source_raw_sha256": self.source_raw_sha256,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "source_observed_at": iso(self.source_observed_at),
            "source_classified_at": iso(self.source_classified_at),
            "source_state_fresh_until": iso(self.source_state_fresh_until),
            "candidate": self.candidate.to_dict(),
            "candidate_sha256": self.candidate_sha256,
            "candidate_size": self.candidate_size,
            "available_feature_ids": list(self.available_feature_ids),
            "missing_feature_count": self.missing_feature_count,
            "blocked_feature_count": self.blocked_feature_count,
            "authority": dict(self.authority),
        }


def _candidate_from_admission(
    admission: ReviewedRealFotMobPlayerContextAdmission,
) -> TeamStrengthContextCandidate:
    if type(admission) is not ReviewedRealFotMobPlayerContextAdmission:
        raise RealPlayerContextTeamStrengthHandoffError("source must be exact PR193 admission")
    authority = dict(admission.authority)
    required_true = (
        "availability_array_semantics_authorized",
        "exact_observation_array_semantics_authorized",
        "expected_starting_xi_semantics_authorized",
        "player_identity_authorized",
        "team_side_authorized",
    )
    if any(authority.get(key) is not True for key in required_true):
        raise RealPlayerContextTeamStrengthHandoffError("PR193 semantic authority is incomplete")
    forbidden_true = (
        "bench_semantics_authorized",
        "position_semantics_authorized",
        "team_strength_feature_authorized",
        "probability_inference_authorized",
        "probability_adjustment_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    )
    if any(authority.get(key) is not False for key in forbidden_true):
        raise RealPlayerContextTeamStrengthHandoffError("PR193 authority boundary drift")

    side_team_ids: dict[TeamSide, int] = {}
    for record_set in admission.record_sets:
        previous = side_team_ids.get(record_set.team_side)
        if previous is not None and previous != record_set.source_team_id:
            raise RealPlayerContextTeamStrengthHandoffError(
                "one team side binds multiple provider teams"
            )
        side_team_ids[record_set.team_side] = record_set.source_team_id
    if set(side_team_ids) != {TeamSide.HOME, TeamSide.AWAY}:
        raise RealPlayerContextTeamStrengthHandoffError("exact HOME/AWAY team identity missing")

    team_ids = {
        side: _source_identity("FOTMOB_TEAM", source_team_id)
        for side, source_team_id in side_team_ids.items()
    }
    player_records: list[PlayerRecordCandidate] = []
    for record in admission.records:
        if record.scope is PlayerContextSetScope.STARTING_XI:
            kind = PlayerRecordKind.STARTER
            unavailable_reason = None
        elif record.scope is PlayerContextSetScope.UNAVAILABLE:
            kind = PlayerRecordKind.UNAVAILABLE
            unavailable_reason = record.unavailability_type
        else:
            raise RealPlayerContextTeamStrengthHandoffError(
                "unreviewed player scope cannot enter handoff"
            )
        player_records.append(
            PlayerRecordCandidate(
                team_id=team_ids[record.team_side],
                player_id=_source_identity("FOTMOB_PLAYER", record.provider_player_id),
                kind=kind,
                lineup_state=LineupState.UNVERIFIED_LINEUP_STATE,
                source_position=None,
                position_group=PositionGroup.UNKNOWN,
                unavailable_reason=unavailable_reason,
                evidence=EvidenceAnchor(
                    source_reference=(
                        f"fotmob-real-player-context:{admission.raw_sha256}:"
                        f"{record.source_record_pointer}"
                    ),
                    observed_at=admission.observed_at,
                    evidence_sha256=record.evidence_sha256,
                ),
                availability_conflicted=False,
                evidence_status=EvidenceStatus.SUPPORTED,
                valid_through=admission.classified_at,
            )
        )

    availability: dict[TeamSide, CompletenessReceiptCandidate] = {}
    for record_set in admission.record_sets:
        if record_set.scope is not PlayerContextSetScope.UNAVAILABLE:
            continue
        anchor = EvidenceAnchor(
            source_reference=(
                f"fotmob-real-player-context-completeness:{admission.raw_sha256}:"
                f"{record_set.array_root_pointer}"
            ),
            observed_at=admission.observed_at,
            evidence_sha256=record_set.evidence_sha256,
        )
        availability[record_set.team_side] = CompletenessReceiptCandidate(
            provider="FOTMOB",
            source_dataset_name=ADMISSION_DATASET_NAME,
            scope=CompletenessScope.CURRENT_AVAILABILITY,
            fixture_identifier=admission.fixture_identifier,
            team_id=team_ids[record_set.team_side],
            as_of=admission.classified_at,
            range_start=admission.observed_at,
            range_end=admission.classified_at,
            fixture_ids=(admission.fixture_identifier,),
            record_count=record_set.record_count,
            evidence=(anchor,),
        )
    if set(availability) != {TeamSide.HOME, TeamSide.AWAY}:
        raise RealPlayerContextTeamStrengthHandoffError(
            "exact availability completeness is missing"
        )

    try:
        return build_team_strength_context_candidate(
            fixture_identifier=admission.fixture_identifier,
            home_team_id=team_ids[TeamSide.HOME],
            away_team_id=team_ids[TeamSide.AWAY],
            kickoff=admission.kickoff,
            as_of=admission.classified_at,
            home_lineup_state=LineupState.UNVERIFIED_LINEUP_STATE,
            away_lineup_state=LineupState.UNVERIFIED_LINEUP_STATE,
            player_records=tuple(player_records),
            historical_appearances=(),
            historical_fixtures=(),
            base_components=(),
            supported_context=(),
            home_availability_completeness=availability[TeamSide.HOME],
            away_availability_completeness=availability[TeamSide.AWAY],
            home_schedule_history_completeness=None,
            away_schedule_history_completeness=None,
            home_player_history_completeness=None,
            away_player_history_completeness=None,
        )
    except TeamStrengthContextError as exc:
        raise RealPlayerContextTeamStrengthHandoffError(
            "PR190 candidate reconstruction failed"
        ) from exc


def build_reviewed_real_fotmob_team_strength_handoff(
    *,
    campaign_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    persisted_receipt_bytes: Any,
    structure_assessment_bytes: Any,
) -> ReviewedRealFotMobTeamStrengthHandoff:
    try:
        admission = build_reviewed_real_fotmob_player_context_admission(
            campaign_receipt_bytes=campaign_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            persisted_receipt_bytes=persisted_receipt_bytes,
            structure_assessment_bytes=structure_assessment_bytes,
        )
        admission_bytes = canonical_reviewed_real_fotmob_player_context_admission_bytes(admission)
    except Exception as exc:
        raise RealPlayerContextTeamStrengthHandoffError(
            "exact PR193 source replay failed"
        ) from exc

    candidate = _candidate_from_admission(admission)
    candidate_bytes = canonical_team_strength_context_candidate_bytes(candidate)
    available = tuple(
        sorted(
            item.feature_id.value
            for item in candidate.features
            if item.status is FeatureStatus.AVAILABLE
        )
    )
    return _new(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        handoff_scope=HANDOFF_SCOPE,
        source_admission_sha256=_sha(admission_bytes),
        source_admission_size=len(admission_bytes),
        source_raw_sha256=admission.raw_sha256,
        fixture_identifier=admission.fixture_identifier,
        source_match_id=admission.source_match_id,
        home_team_id=candidate.home_team_id,
        away_team_id=candidate.away_team_id,
        source_observed_at=admission.observed_at,
        source_classified_at=admission.classified_at,
        source_state_fresh_until=admission.classified_at,
        candidate=candidate,
        candidate_sha256=_sha(candidate_bytes),
        candidate_size=len(candidate_bytes),
        available_feature_ids=available,
        missing_feature_count=sum(
            item.status is FeatureStatus.MISSING for item in candidate.features
        ),
        blocked_feature_count=sum(
            item.status is FeatureStatus.BLOCKED for item in candidate.features
        ),
        authority=types.MappingProxyType(dict(_AUTHORITY)),
    )


def canonical_reviewed_real_fotmob_team_strength_handoff_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedRealFotMobTeamStrengthHandoff:
        raise RealPlayerContextTeamStrengthHandoffError(
            "value must be exact reviewed handoff"
        )
    canonical_team_strength_context_candidate_bytes(value.candidate)
    value.__post_init__()
    return _canonical(value.to_dict())


def sha256_reviewed_real_fotmob_team_strength_handoff(value: Any) -> str:
    return _sha(canonical_reviewed_real_fotmob_team_strength_handoff_bytes(value))
