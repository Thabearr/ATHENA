"""Authoritative adapter from reviewed FotMob arrays to the PR190 candidate.

Only this source-replaying wrapper may authorize the nested team-strength
feature boundary.  The PR190 object remains candidate-only and all-false.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import types
from typing import Any, Mapping

from domain.fotmob_reviewed_match_details_array_records import (
    DATASET_NAME as ARRAY_DATASET_NAME,
    ArrayRecordSetScope,
    ReviewedArrayEvidenceStatus,
    ReviewedMatchDetailsArrayRecords,
    ReviewedMatchDetailsArrayRecordsError,
    canonical_reviewed_match_details_array_records_bytes,
    revalidate_reviewed_match_details_array_records,
)
from domain.fixture_model_features import ModelFeatureId, ModelFeatureStatus
from domain.fotmob_reviewed_match_details_fixture_intelligence_snapshot import (
    FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError,
    ReviewedMatchDetailsFixtureIntelligenceSnapshot,
    canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes,
    revalidate_reviewed_match_details_fixture_intelligence_snapshot,
)
from domain.fotmob_reviewed_match_details_model_feature_handoff import (
    FotMobReviewedMatchDetailsModelFeatureHandoffError,
    ReviewedMatchDetailsModelFeatureHandoff,
    canonical_reviewed_match_details_model_feature_handoff_bytes,
    revalidate_reviewed_match_details_model_feature_handoff,
)
from domain.fotmob_team_strength_fixture_intelligence import (
    BaseStrengthComponent,
    BaseStrengthComponentId,
    CompletenessReceiptCandidate,
    CompletenessScope,
    EvidenceAnchor,
    EvidenceStatus,
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
DATASET_NAME = "athena-fotmob-reviewed-team-strength-context-adapter-v1"
ADAPTER_SCOPE = "EXACT_REVALIDATED_MATCH_DETAILS_ARRAY_OBSERVATION_ONLY"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_SAFETY = tuple(
    sorted(
        {
            "bet_authorized": False,
            "pricing_authorized": False,
            "probability_adjustment_authorized": False,
            "probability_inference_authorized": False,
            "production_approval_authorized": False,
            "selection_authorized": False,
            "team_strength_feature_authorized": True,
        }.items()
    )
)


class ReviewedTeamStrengthContextAdapterError(ValueError):
    pass


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ReviewedTeamStrengthContextAdapterError(f"{label} must be lowercase SHA-256")
    return value


def _positive(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ReviewedTeamStrengthContextAdapterError(f"{label} must be positive integer")
    return value


def _canonical(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReviewedTeamStrengthContextAdapterError("adapter canonicalization failed") from exc


def _source_identity(prefix: str, value: str | int) -> str:
    kind = "INTEGER" if type(value) is int else "STRING"
    return f"{prefix}:{kind}:{value}"


def _record_kind(scope: ArrayRecordSetScope) -> PlayerRecordKind:
    return {
        ArrayRecordSetScope.STARTING_XI: PlayerRecordKind.STARTER,
        ArrayRecordSetScope.BENCH: PlayerRecordKind.BENCH,
        ArrayRecordSetScope.UNAVAILABLE: PlayerRecordKind.UNAVAILABLE,
    }[scope]


def _evidence_status(status: ReviewedArrayEvidenceStatus) -> EvidenceStatus:
    return {
        ReviewedArrayEvidenceStatus.SUPPORTED: EvidenceStatus.SUPPORTED,
        ReviewedArrayEvidenceStatus.STALE: EvidenceStatus.STALE,
        ReviewedArrayEvidenceStatus.CONFLICTED: EvidenceStatus.CONFLICTED,
        ReviewedArrayEvidenceStatus.UNVERIFIED: EvidenceStatus.UNVERIFIED,
    }[status]


def _lineup_state(array: ReviewedMatchDetailsArrayRecords, side: TeamSide) -> LineupState:
    complete_scopes = {
        receipt.scope
        for receipt in array.completeness_receipts
        if receipt.team_side is side
        and receipt.scope in {ArrayRecordSetScope.STARTING_XI, ArrayRecordSetScope.BENCH}
        and array.classified_at
        <= next(
            decision.fresh_until
            for decision in array.decisions
            if decision.team_side is side and decision.scope is receipt.scope
        )
    }
    if complete_scopes != {ArrayRecordSetScope.STARTING_XI, ArrayRecordSetScope.BENCH}:
        return LineupState.UNVERIFIED_LINEUP_STATE
    relevant = tuple(
        record for record in array.records
        if record.team_side is side
        and record.scope in {ArrayRecordSetScope.STARTING_XI, ArrayRecordSetScope.BENCH}
    )
    if not relevant or any(record.evidence_status is not ReviewedArrayEvidenceStatus.SUPPORTED for record in relevant):
        return LineupState.UNVERIFIED_LINEUP_STATE
    states = {record.lineup_state for record in relevant}
    if len(states) != 1 or LineupState.UNVERIFIED_LINEUP_STATE in states:
        return LineupState.UNVERIFIED_LINEUP_STATE
    return next(iter(states))


def _new_reviewed_context(**values: Any) -> ReviewedFotMobTeamStrengthContext:
    value = object.__new__(ReviewedFotMobTeamStrengthContext)
    expected = {field.name for field in dataclasses.fields(ReviewedFotMobTeamStrengthContext)}
    if set(values) != expected:
        raise ReviewedTeamStrengthContextAdapterError("internal authoritative field set drift")
    for name, item in values.items():
        object.__setattr__(value, name, item)
    value.__post_init__()
    return value


@dataclasses.dataclass(frozen=True, init=False)
class ReviewedFotMobTeamStrengthContext:
    schema_version: int
    dataset_name: str
    adapter_scope: str
    source_array_artifact_sha256: str
    source_array_artifact_size: int
    source_raw_sha256: str
    source_pr65_artifact_sha256: str
    source_pr65_artifact_size: int
    source_pr66_handoff_sha256: str
    source_pr66_handoff_size: int
    source_fixture_intelligence_snapshot_sha256: str
    source_model_feature_snapshot_sha256: str
    fixture_identifier: str
    source_match_id: str
    home_team_id: str
    away_team_id: str
    candidate: TeamStrengthContextCandidate
    candidate_sha256: str
    candidate_size: int
    safety: Mapping[str, bool]

    def __init__(self, *_: Any, **__: Any) -> None:
        raise ReviewedTeamStrengthContextAdapterError(
            "authoritative wrapper can only be created by exact source replay"
        )

    def __post_init__(self) -> None:
        if (self.schema_version, self.dataset_name, self.adapter_scope) != (SCHEMA_VERSION, DATASET_NAME, ADAPTER_SCOPE):
            raise ReviewedTeamStrengthContextAdapterError("adapter identity drift")
        _sha(self.source_array_artifact_sha256, "source_array_artifact_sha256")
        _positive(self.source_array_artifact_size, "source_array_artifact_size")
        _sha(self.source_raw_sha256, "source_raw_sha256")
        _sha(self.source_pr65_artifact_sha256, "source_pr65_artifact_sha256")
        _positive(self.source_pr65_artifact_size, "source_pr65_artifact_size")
        _sha(self.source_pr66_handoff_sha256, "source_pr66_handoff_sha256")
        _positive(self.source_pr66_handoff_size, "source_pr66_handoff_size")
        _sha(
            self.source_fixture_intelligence_snapshot_sha256,
            "source_fixture_intelligence_snapshot_sha256",
        )
        _sha(self.source_model_feature_snapshot_sha256, "source_model_feature_snapshot_sha256")
        if type(self.fixture_identifier) is not str or not self.fixture_identifier:
            raise ReviewedTeamStrengthContextAdapterError("fixture identifier drift")
        if type(self.source_match_id) is not str or not self.source_match_id:
            raise ReviewedTeamStrengthContextAdapterError("source match identity drift")
        if type(self.home_team_id) is not str or type(self.away_team_id) is not str or self.home_team_id == self.away_team_id:
            raise ReviewedTeamStrengthContextAdapterError("adapter team identity drift")
        if type(self.candidate) is not TeamStrengthContextCandidate:
            raise ReviewedTeamStrengthContextAdapterError("nested value must be exact PR190 candidate")
        if (self.candidate.fixture_identifier, self.candidate.home_team_id, self.candidate.away_team_id) != (self.fixture_identifier, self.home_team_id, self.away_team_id):
            raise ReviewedTeamStrengthContextAdapterError("nested fixture/team identity drift")
        candidate_bytes = canonical_team_strength_context_candidate_bytes(self.candidate)
        if self.candidate_sha256 != hashlib.sha256(candidate_bytes).hexdigest() or self.candidate_size != len(candidate_bytes):
            raise ReviewedTeamStrengthContextAdapterError("nested candidate canonical identity drift")
        if any(value for value in dict(self.candidate.safety).values()):
            raise ReviewedTeamStrengthContextAdapterError("nested PR190 candidate safety must remain all false")
        if tuple(self.safety.items()) != _SAFETY:
            raise ReviewedTeamStrengthContextAdapterError("adapter safety/authority drift")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "adapter_scope": self.adapter_scope,
            "source_array_artifact_sha256": self.source_array_artifact_sha256,
            "source_array_artifact_size": self.source_array_artifact_size,
            "source_raw_sha256": self.source_raw_sha256,
            "source_pr65_artifact_sha256": self.source_pr65_artifact_sha256,
            "source_pr65_artifact_size": self.source_pr65_artifact_size,
            "source_pr66_handoff_sha256": self.source_pr66_handoff_sha256,
            "source_pr66_handoff_size": self.source_pr66_handoff_size,
            "source_fixture_intelligence_snapshot_sha256": self.source_fixture_intelligence_snapshot_sha256,
            "source_model_feature_snapshot_sha256": self.source_model_feature_snapshot_sha256,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "candidate": self.candidate.to_dict(),
            "candidate_sha256": self.candidate_sha256,
            "candidate_size": self.candidate_size,
            "safety": dict(self.safety),
        }


def _build_from_array(
    array: ReviewedMatchDetailsArrayRecords,
    exact_array_bytes: bytes,
    pr65: ReviewedMatchDetailsFixtureIntelligenceSnapshot,
    exact_pr65_bytes: bytes,
    handoff: ReviewedMatchDetailsModelFeatureHandoff,
    exact_handoff_bytes: bytes,
) -> ReviewedFotMobTeamStrengthContext:
    side_team_ids: dict[TeamSide, str | int] = {}
    for decision in array.decisions:
        previous = side_team_ids.get(decision.team_side)
        if previous is not None and previous != decision.source_team_id:
            raise ReviewedTeamStrengthContextAdapterError("one fixture side cannot bind multiple provider teams")
        side_team_ids[decision.team_side] = decision.source_team_id
    if set(side_team_ids) != {TeamSide.HOME, TeamSide.AWAY}:
        raise ReviewedTeamStrengthContextAdapterError("array review must bind exact home and away provider teams")
    home_team_id = _source_identity("FOTMOB_TEAM", side_team_ids[TeamSide.HOME])
    away_team_id = _source_identity("FOTMOB_TEAM", side_team_ids[TeamSide.AWAY])
    team_ids = {TeamSide.HOME: home_team_id, TeamSide.AWAY: away_team_id}
    lineup_states = {side: _lineup_state(array, side) for side in TeamSide}
    position_map = {item.source_value: item.position_group for item in array.position_mappings}
    player_records: list[PlayerRecordCandidate] = []
    for record in array.records:
        kind = _record_kind(record.scope)
        source_ref = (
            f"fotmob-match-details:{array.raw_sha256}:{record.record_pointer_pattern}:"
            + ".".join(str(value) for value in record.source_coordinate)
        )
        player_records.append(PlayerRecordCandidate(
            team_id=team_ids[record.team_side],
            player_id=_source_identity("FOTMOB_PLAYER", record.provider_player_id),
            kind=kind,
            lineup_state=lineup_states[record.team_side],
            source_position=record.source_position,
            position_group=position_map.get(record.source_position, PositionGroup.UNKNOWN),
            unavailable_reason=record.unavailable_reason if kind is PlayerRecordKind.UNAVAILABLE else None,
            evidence=EvidenceAnchor(source_ref, array.observed_at, record.evidence_sha256),
            availability_conflicted=False,
            evidence_status=_evidence_status(record.evidence_status),
            valid_through=record.fresh_until,
        ))
    raw_anchor = EvidenceAnchor(
        f"fotmob-match-details-raw:{array.source_match_id}", array.observed_at, array.raw_sha256
    )
    feature_snapshot_anchor = EvidenceAnchor(
        f"fotmob-reviewed-model-features:{handoff.model_feature_snapshot_sha256}",
        handoff.as_of,
        handoff.model_feature_snapshot_sha256,
    )
    feature_index = {
        item.feature_id: item for item in handoff.model_feature_snapshot.features
    }
    base_bindings = (
        (ModelFeatureId.HOME_FORM, home_team_id, BaseStrengthComponentId.FORM),
        (ModelFeatureId.AWAY_FORM, away_team_id, BaseStrengthComponentId.FORM),
        (ModelFeatureId.HOME_ELO, home_team_id, BaseStrengthComponentId.ELO),
        (ModelFeatureId.AWAY_ELO, away_team_id, BaseStrengthComponentId.ELO),
    )
    base_components = tuple(
        BaseStrengthComponent(
            team_id=team_id,
            component_id=component_id,
            value=feature_index[feature_id].value,
            evidence=feature_snapshot_anchor,
            evidence_status=EvidenceStatus.SUPPORTED,
        )
        for feature_id, team_id, component_id in base_bindings
        if feature_index[feature_id].status is ModelFeatureStatus.AVAILABLE
    )
    availability_receipts: dict[TeamSide, CompletenessReceiptCandidate | None] = {
        TeamSide.HOME: None,
        TeamSide.AWAY: None,
    }
    for receipt in array.completeness_receipts:
        if receipt.scope is not ArrayRecordSetScope.UNAVAILABLE:
            continue
        decision = next(
            item for item in array.decisions
            if item.scope is receipt.scope and item.team_side is receipt.team_side
        )
        status = ReviewedArrayEvidenceStatus.SUPPORTED if array.classified_at <= decision.fresh_until else ReviewedArrayEvidenceStatus.STALE
        if status is not ReviewedArrayEvidenceStatus.SUPPORTED:
            continue
        availability_receipts[receipt.team_side] = CompletenessReceiptCandidate(
            provider="FOTMOB",
            source_dataset_name=ARRAY_DATASET_NAME,
            scope=CompletenessScope.CURRENT_AVAILABILITY,
            fixture_identifier=array.fixture_identifier,
            team_id=team_ids[receipt.team_side],
            as_of=array.classified_at,
            range_start=array.observed_at,
            range_end=array.classified_at,
            fixture_ids=(array.fixture_identifier,),
            record_count=receipt.record_count,
            evidence=(raw_anchor,),
        )
    try:
        candidate = build_team_strength_context_candidate(
            fixture_identifier=array.fixture_identifier,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            kickoff=array.kickoff,
            as_of=array.classified_at,
            home_lineup_state=lineup_states[TeamSide.HOME],
            away_lineup_state=lineup_states[TeamSide.AWAY],
            player_records=tuple(player_records),
            historical_appearances=(),
            historical_fixtures=(),
            base_components=base_components,
            supported_context=(),
            home_availability_completeness=availability_receipts[TeamSide.HOME],
            away_availability_completeness=availability_receipts[TeamSide.AWAY],
            home_schedule_history_completeness=None,
            away_schedule_history_completeness=None,
            home_player_history_completeness=None,
            away_player_history_completeness=None,
        )
        candidate_bytes = canonical_team_strength_context_candidate_bytes(candidate)
    except TeamStrengthContextError as exc:
        raise ReviewedTeamStrengthContextAdapterError("PR190 candidate reconstruction failed") from exc
    return _new_reviewed_context(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        adapter_scope=ADAPTER_SCOPE,
        source_array_artifact_sha256=hashlib.sha256(exact_array_bytes).hexdigest(),
        source_array_artifact_size=len(exact_array_bytes),
        source_raw_sha256=array.raw_sha256,
        source_pr65_artifact_sha256=hashlib.sha256(exact_pr65_bytes).hexdigest(),
        source_pr65_artifact_size=len(exact_pr65_bytes),
        source_pr66_handoff_sha256=hashlib.sha256(exact_handoff_bytes).hexdigest(),
        source_pr66_handoff_size=len(exact_handoff_bytes),
        source_fixture_intelligence_snapshot_sha256=pr65.snapshot_sha256,
        source_model_feature_snapshot_sha256=handoff.model_feature_snapshot_sha256,
        fixture_identifier=array.fixture_identifier,
        source_match_id=array.source_match_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        candidate=candidate,
        candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
        candidate_size=len(candidate_bytes),
        safety=types.MappingProxyType(dict(_SAFETY)),
    )


def build_reviewed_fotmob_team_strength_context(
    *, evidence: Any, evidence_receipt_bytes: Any, manifest_bytes: Any, raw_bytes: Any,
    assessment: Any, assessment_bytes: Any, array_artifact: Any, array_artifact_bytes: Any,
    materialization_inputs: Any, candidate_set: Any, candidate_set_bytes: Any,
    admission: Any, admission_bytes: Any, pr65_artifact: Any, pr65_artifact_bytes: Any,
    pr66_handoff: Any, pr66_handoff_bytes: Any,
) -> ReviewedFotMobTeamStrengthContext:
    try:
        rebuilt = revalidate_reviewed_match_details_array_records(
            evidence=evidence, evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes, raw_bytes=raw_bytes, assessment=assessment,
            assessment_bytes=assessment_bytes, artifact=array_artifact,
            artifact_bytes=array_artifact_bytes,
        )
        exact_array_bytes = canonical_reviewed_match_details_array_records_bytes(rebuilt)
        rebuilt_pr65 = revalidate_reviewed_match_details_fixture_intelligence_snapshot(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
            artifact=pr65_artifact,
            artifact_bytes=pr65_artifact_bytes,
        )
        exact_pr65_bytes = canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes(
            rebuilt_pr65
        )
        rebuilt_handoff = revalidate_reviewed_match_details_model_feature_handoff(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
            artifact=rebuilt_pr65,
            artifact_bytes=exact_pr65_bytes,
            handoff=pr66_handoff,
            handoff_bytes=pr66_handoff_bytes,
        )
        exact_handoff_bytes = canonical_reviewed_match_details_model_feature_handoff_bytes(
            rebuilt_handoff
        )
    except (
        ReviewedMatchDetailsArrayRecordsError,
        FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError,
        FotMobReviewedMatchDetailsModelFeatureHandoffError,
    ) as exc:
        raise ReviewedTeamStrengthContextAdapterError(
            "reviewed PR52→PR66 plus array lineage failed full replay"
        ) from exc
    if (
        rebuilt.fixture_identifier,
        rebuilt.source_match_id,
        rebuilt.kickoff,
        rebuilt.classified_at,
    ) != (
        rebuilt_pr65.fixture_identifier,
        rebuilt_pr65.source_match_id,
        rebuilt_pr65.kickoff,
        rebuilt_pr65.classified_at,
    ) or (
        rebuilt.fixture_identifier,
        rebuilt.source_match_id,
        rebuilt.kickoff,
        rebuilt.classified_at,
    ) != (
        rebuilt_handoff.fixture_identifier,
        rebuilt_handoff.source_match_id,
        rebuilt_handoff.kickoff,
        rebuilt_handoff.as_of,
    ):
        raise ReviewedTeamStrengthContextAdapterError(
            "array, PR65 and PR66 fixture/source/kickoff/as-of identity mismatch"
        )
    exact_array_member = tuple(
        item
        for item in materialization_inputs
        if getattr(getattr(item, "evidence", None), "raw_sha256", None) == rebuilt.raw_sha256
        and hashlib.sha256(getattr(item, "assessment_bytes", b"")).hexdigest()
        == rebuilt.structure_sha256
    )
    if not exact_array_member:
        raise ReviewedTeamStrengthContextAdapterError(
            "exact array raw/PR53 observation is absent from admitted PR65 materialization inputs"
        )
    return _build_from_array(
        rebuilt,
        exact_array_bytes,
        rebuilt_pr65,
        exact_pr65_bytes,
        rebuilt_handoff,
        exact_handoff_bytes,
    )


def canonical_reviewed_fotmob_team_strength_context_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedFotMobTeamStrengthContext:
        raise ReviewedTeamStrengthContextAdapterError("value must be exact reviewed adapter wrapper")
    canonical_team_strength_context_candidate_bytes(value.candidate)
    value.__post_init__()
    return _canonical(value.to_dict())


def sha256_reviewed_fotmob_team_strength_context(value: Any) -> str:
    return hashlib.sha256(canonical_reviewed_fotmob_team_strength_context_bytes(value)).hexdigest()


def revalidate_reviewed_fotmob_team_strength_context(
    *, evidence: Any, evidence_receipt_bytes: Any, manifest_bytes: Any, raw_bytes: Any,
    assessment: Any, assessment_bytes: Any, array_artifact: Any, array_artifact_bytes: Any,
    materialization_inputs: Any, candidate_set: Any, candidate_set_bytes: Any,
    admission: Any, admission_bytes: Any, pr65_artifact: Any, pr65_artifact_bytes: Any,
    pr66_handoff: Any, pr66_handoff_bytes: Any,
    context: Any, context_bytes: Any,
) -> ReviewedFotMobTeamStrengthContext:
    if type(context) is not ReviewedFotMobTeamStrengthContext or type(context_bytes) is not bytes:
        raise ReviewedTeamStrengthContextAdapterError("context/object bytes must be exact immutable values")
    supplied = canonical_reviewed_fotmob_team_strength_context_bytes(context)
    rebuilt = build_reviewed_fotmob_team_strength_context(
        evidence=evidence, evidence_receipt_bytes=evidence_receipt_bytes,
        manifest_bytes=manifest_bytes, raw_bytes=raw_bytes, assessment=assessment,
        assessment_bytes=assessment_bytes, array_artifact=array_artifact,
        array_artifact_bytes=array_artifact_bytes,
        materialization_inputs=materialization_inputs, candidate_set=candidate_set,
        candidate_set_bytes=candidate_set_bytes, admission=admission,
        admission_bytes=admission_bytes, pr65_artifact=pr65_artifact,
        pr65_artifact_bytes=pr65_artifact_bytes, pr66_handoff=pr66_handoff,
        pr66_handoff_bytes=pr66_handoff_bytes,
    )
    exact = canonical_reviewed_fotmob_team_strength_context_bytes(rebuilt)
    if supplied != exact or context_bytes != exact:
        raise ReviewedTeamStrengthContextAdapterError("reviewed team-strength context differs from full replay")
    return rebuilt


__all__ = [
    "ADAPTER_SCOPE", "DATASET_NAME", "ReviewedFotMobTeamStrengthContext",
    "ReviewedTeamStrengthContextAdapterError", "SCHEMA_VERSION",
    "build_reviewed_fotmob_team_strength_context",
    "canonical_reviewed_fotmob_team_strength_context_bytes",
    "revalidate_reviewed_fotmob_team_strength_context",
    "sha256_reviewed_fotmob_team_strength_context",
]
