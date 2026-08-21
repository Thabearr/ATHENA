"""Authorize exact real FotMob team-strength features through PR65/PR66 lineage.

This boundary replays the frozen PR192 evidence through PR193 and PR194, then
constructs one exact scalar Fixture Intelligence lineage over the *same raw
match-details observation*.  The scalar is the already-reviewed
``/content/lineup/lineupType == "predicted"`` value and exists only to carry the
exact raw/PR53 observation through PR54→PR66 without inventing a model feature.

Only after that complete ancestry is proven does this wrapper authorize the
nested PR190 team-strength feature candidate for the exact classification
instant.  It does not authorize probability adjustment, expected-goals use,
pricing, selection, BET, or prospective reuse after the source freshness
instant.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
import types
from typing import Any, Mapping

from domain.fixture_intelligence import (
    IntelligenceCategory,
    IntelligenceFactStatus,
)
from domain.fixture_model_features import ModelFeatureStatus
from domain.fotmob_real_player_context_array_admission import (
    CLASSIFIED_AT as PR193_CLASSIFIED_AT,
    FIXTURE_IDENTIFIER as PR193_FIXTURE_IDENTIFIER,
    KICKOFF as PR193_KICKOFF,
    OBSERVED_AT as PR193_OBSERVED_AT,
    RAW_SHA256 as PR193_RAW_SHA256,
    SOURCE_MATCH_ID as PR193_SOURCE_MATCH_ID,
    STRUCTURE_SHA256 as PR193_STRUCTURE_SHA256,
)
from domain.fotmob_real_player_context_team_strength_handoff import (
    EXPECTED_AWAY_TEAM_ID,
    EXPECTED_CANDIDATE_SHA256,
    EXPECTED_HOME_TEAM_ID,
    SOURCE_ADMISSION_SHA256,
    ReviewedRealFotMobTeamStrengthHandoff,
    build_reviewed_real_fotmob_team_strength_handoff,
    canonical_reviewed_real_fotmob_team_strength_handoff_bytes,
)
from domain.fotmob_reviewed_match_details_fact_status_materializer import (
    canonical_reviewed_match_details_fact_status_materialization_bytes,
    materialize_reviewed_match_details_fact_statuses,
)
from domain.fotmob_reviewed_match_details_field_evidence_qualification import (
    FieldEvidenceQualificationDisposition,
    MatchDetailsFieldEvidenceReviewDecision,
    build_reviewed_match_details_field_evidence_qualification,
    canonical_reviewed_match_details_field_evidence_qualification_bytes,
)
from domain.fotmob_reviewed_match_details_field_review import (
    FieldReviewDisposition,
    MatchDetailsFieldReviewDecision,
    build_reviewed_match_details_field_semantics,
    canonical_reviewed_match_details_field_semantics_bytes,
)
from domain.fotmob_reviewed_match_details_fixture_intelligence_snapshot import (
    ReviewedMatchDetailsFixtureIntelligenceSnapshot,
    build_reviewed_match_details_fixture_intelligence_snapshot,
    canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes,
)
from domain.fotmob_reviewed_match_details_model_feature_handoff import (
    ReviewedMatchDetailsModelFeatureHandoff,
    build_reviewed_match_details_model_feature_handoff,
    canonical_reviewed_match_details_model_feature_handoff_bytes,
)
from domain.fotmob_reviewed_match_details_persisted_evidence import (
    canonical_persisted_match_details_evidence_receipt_bytes,
    verify_persisted_match_details_evidence,
)
from domain.fotmob_reviewed_match_details_snapshot_candidate_admission import (
    SnapshotCandidateAdmissionDisposition,
    SnapshotCandidateCompletenessAttestation,
    admit_reviewed_match_details_snapshot_candidate_set,
    canonical_reviewed_match_details_snapshot_candidate_admission_bytes,
)
from domain.fotmob_reviewed_match_details_snapshot_candidate_set import (
    ReviewedMatchDetailsMaterializationChainInput,
    build_reviewed_match_details_snapshot_candidate_set,
    canonical_reviewed_match_details_snapshot_candidate_set_bytes,
)
from domain.fotmob_reviewed_match_details_status_classification_policy import (
    MatchDetailsFreshnessPolicyRule,
    build_reviewed_match_details_status_classification_policy,
    canonical_reviewed_match_details_status_classification_policy_bytes,
)
from domain.fotmob_reviewed_match_details_status_evaluator import (
    canonical_reviewed_match_details_status_evaluation_bytes,
    evaluate_reviewed_match_details_status_policy,
)
from domain.fotmob_reviewed_match_details_structure import (
    JsonValueKind,
    assess_reviewed_match_details_structure,
    canonical_reviewed_match_details_structure_bytes,
)
from domain.fotmob_reviewed_match_details_unverified_candidates import (
    build_reviewed_match_details_unverified_candidates,
    canonical_reviewed_match_details_unverified_candidate_bundle_bytes,
)
from domain.fotmob_reviewed_match_details_unverified_facts import (
    build_reviewed_match_details_unverified_fact_bundle,
    canonical_reviewed_match_details_unverified_fact_bundle_bytes,
)
from domain.fotmob_team_strength_fixture_intelligence import (
    FeatureStatus,
    LineupState,
    PositionGroup,
    TeamStrengthContextCandidate,
    canonical_team_strength_context_candidate_bytes,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-real-player-context-authoritative-bridge-v1"
BRIDGE_SCOPE = "EXACT_PR193_OBSERVATION_PR65_PR66_TEAM_STRENGTH_AUTHORITY_ONLY"
LINEAGE_SCALAR_POINTER = "/content/lineup/lineupType"
LINEAGE_SCALAR_FIELD = "source_lineup_type"
LINEAGE_SCALAR_VALUE = "predicted"
LINEAGE_REVIEWER_REFERENCE = "ATHENA_PR197_REUSE_PR193_LINEUP_TYPE_REVIEW"
LINEAGE_QUALIFICATION_REFERENCE = "ATHENA_PR197_EXACT_SCALAR_QUALIFICATION"
LINEAGE_POLICY_REFERENCE = "ATHENA_PR197_EXACT_SCALAR_FRESHNESS_POLICY"
LINEAGE_ADMISSION_REFERENCE = "ATHENA_PR197_EXACT_WHOLE_SET_ADMISSION"
SOURCE_PR194_HANDOFF_SHA256 = "b5aab660cb4aebca6c1fd9b0d8bfb2d4e422d614e2fe4c59e796a2e670957ff3"
_SHA = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

_AUTHORITY = tuple(
    sorted(
        {
            "bet_authorized": False,
            "bench_semantics_used": False,
            "historical_player_evidence_used": False,
            "lineage_scalar_model_feature_authorized": False,
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


class RealPlayerContextAuthoritativeBridgeError(ValueError):
    """Raised when exact real player-context authority cannot be replayed."""


def _sha(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise RealPlayerContextAuthoritativeBridgeError("hash input must be exact bytes")
    return hashlib.sha256(raw).hexdigest()


def _require_sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise RealPlayerContextAuthoritativeBridgeError(f"{label} must be lowercase SHA-256")
    return value


def _positive(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise RealPlayerContextAuthoritativeBridgeError(f"{label} must be positive integer")
    return value


def _utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime) or value.tzinfo is not dt.timezone.utc:
        raise RealPlayerContextAuthoritativeBridgeError(
            f"{label} must already use exact datetime.timezone.utc"
        )
    return value


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
        raise RealPlayerContextAuthoritativeBridgeError(
            "authoritative bridge canonicalization failed"
        ) from exc


def _new(**values: Any) -> "ReviewedRealFotMobAuthoritativeTeamStrengthBridge":
    obj = object.__new__(ReviewedRealFotMobAuthoritativeTeamStrengthBridge)
    expected = {
        field.name
        for field in dataclasses.fields(ReviewedRealFotMobAuthoritativeTeamStrengthBridge)
    }
    if set(values) != expected:
        raise RealPlayerContextAuthoritativeBridgeError("internal bridge field drift")
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    obj.__post_init__()
    return obj


@dataclasses.dataclass(frozen=True, init=False)
class ReviewedRealFotMobAuthoritativeTeamStrengthBridge:
    schema_version: int
    dataset_name: str
    bridge_scope: str
    source_pr193_admission_sha256: str
    source_pr194_handoff_sha256: str
    source_pr194_handoff_size: int
    source_raw_sha256: str
    source_structure_sha256: str
    fixture_identifier: str
    source_match_id: str
    home_team_id: str
    away_team_id: str
    source_observed_at: dt.datetime
    source_classified_at: dt.datetime
    source_state_fresh_until: dt.datetime
    lineage_scalar_pointer: str
    lineage_scalar_field: str
    lineage_scalar_value: str
    source_field_review_sha256: str
    source_qualification_sha256: str
    source_policy_sha256: str
    source_evaluation_sha256: str
    source_materialization_sha256: str
    source_materialization_size: int
    source_candidate_set_sha256: str
    source_candidate_set_size: int
    source_candidate_admission_sha256: str
    source_candidate_admission_size: int
    source_pr65_artifact_sha256: str
    source_pr65_artifact_size: int
    source_pr66_handoff_sha256: str
    source_pr66_handoff_size: int
    source_fixture_intelligence_snapshot_sha256: str
    source_model_feature_snapshot_sha256: str
    candidate: TeamStrengthContextCandidate
    candidate_sha256: str
    candidate_size: int
    available_feature_ids: tuple[str, ...]
    authority: Mapping[str, bool]

    def __init__(self, *_: Any, **__: Any) -> None:
        raise RealPlayerContextAuthoritativeBridgeError(
            "authoritative bridge can only be created by exact PR192→PR66 source replay"
        )

    def __post_init__(self) -> None:
        if (self.schema_version, self.dataset_name, self.bridge_scope) != (
            SCHEMA_VERSION,
            DATASET_NAME,
            BRIDGE_SCOPE,
        ):
            raise RealPlayerContextAuthoritativeBridgeError("bridge identity drift")
        for label in (
            "source_pr193_admission_sha256",
            "source_pr194_handoff_sha256",
            "source_raw_sha256",
            "source_structure_sha256",
            "source_field_review_sha256",
            "source_qualification_sha256",
            "source_policy_sha256",
            "source_evaluation_sha256",
            "source_materialization_sha256",
            "source_candidate_set_sha256",
            "source_candidate_admission_sha256",
            "source_pr65_artifact_sha256",
            "source_pr66_handoff_sha256",
            "source_fixture_intelligence_snapshot_sha256",
            "source_model_feature_snapshot_sha256",
            "candidate_sha256",
        ):
            _require_sha(getattr(self, label), label)
        for label in (
            "source_pr194_handoff_size",
            "source_materialization_size",
            "source_candidate_set_size",
            "source_candidate_admission_size",
            "source_pr65_artifact_size",
            "source_pr66_handoff_size",
            "candidate_size",
        ):
            _positive(getattr(self, label), label)
        observed = _utc(self.source_observed_at, "source_observed_at")
        classified = _utc(self.source_classified_at, "source_classified_at")
        fresh_until = _utc(self.source_state_fresh_until, "source_state_fresh_until")
        if (
            self.source_pr193_admission_sha256 != SOURCE_ADMISSION_SHA256
            or self.source_pr194_handoff_sha256 != SOURCE_PR194_HANDOFF_SHA256
            or self.source_raw_sha256 != PR193_RAW_SHA256
            or self.source_structure_sha256 != PR193_STRUCTURE_SHA256
            or self.fixture_identifier != PR193_FIXTURE_IDENTIFIER
            or self.source_match_id != PR193_SOURCE_MATCH_ID
            or self.home_team_id != EXPECTED_HOME_TEAM_ID
            or self.away_team_id != EXPECTED_AWAY_TEAM_ID
            or observed != PR193_OBSERVED_AT
            or classified != PR193_CLASSIFIED_AT
            or fresh_until != PR193_CLASSIFIED_AT
        ):
            raise RealPlayerContextAuthoritativeBridgeError("exact PR193/PR194 source identity drift")
        if not observed < classified < PR193_KICKOFF:
            raise RealPlayerContextAuthoritativeBridgeError("source chronology drift")
        if (
            self.lineage_scalar_pointer != LINEAGE_SCALAR_POINTER
            or self.lineage_scalar_field != LINEAGE_SCALAR_FIELD
            or self.lineage_scalar_value != LINEAGE_SCALAR_VALUE
        ):
            raise RealPlayerContextAuthoritativeBridgeError("lineage scalar identity drift")
        if type(self.candidate) is not TeamStrengthContextCandidate:
            raise RealPlayerContextAuthoritativeBridgeError("nested candidate type drift")
        candidate_bytes = canonical_team_strength_context_candidate_bytes(self.candidate)
        if (
            _sha(candidate_bytes) != EXPECTED_CANDIDATE_SHA256
            or self.candidate_sha256 != EXPECTED_CANDIDATE_SHA256
            or self.candidate_size != len(candidate_bytes)
        ):
            raise RealPlayerContextAuthoritativeBridgeError("exact PR194 candidate identity drift")
        if (
            self.candidate.fixture_identifier,
            self.candidate.home_team_id,
            self.candidate.away_team_id,
            self.candidate.as_of,
            self.candidate.kickoff,
        ) != (
            PR193_FIXTURE_IDENTIFIER,
            EXPECTED_HOME_TEAM_ID,
            EXPECTED_AWAY_TEAM_ID,
            PR193_CLASSIFIED_AT,
            PR193_KICKOFF,
        ):
            raise RealPlayerContextAuthoritativeBridgeError("nested candidate fixture/team/as-of drift")
        if (
            self.candidate.home_lineup_state is not LineupState.UNVERIFIED_LINEUP_STATE
            or self.candidate.away_lineup_state is not LineupState.UNVERIFIED_LINEUP_STATE
        ):
            raise RealPlayerContextAuthoritativeBridgeError(
                "missing bench must keep aggregate lineup state unverified"
            )
        if any(value for _, value in self.candidate.safety):
            raise RealPlayerContextAuthoritativeBridgeError("nested PR190 safety must remain all false")
        available = {
            item.feature_id.value: item.value
            for item in self.candidate.features
            if item.status is FeatureStatus.AVAILABLE
        }
        if available != _EXPECTED_AVAILABLE_FEATURES:
            raise RealPlayerContextAuthoritativeBridgeError(
                "authoritative candidate exceeds exact admitted current availability semantics"
            )
        if self.available_feature_ids != _EXPECTED_AVAILABLE_FEATURE_IDS:
            raise RealPlayerContextAuthoritativeBridgeError("available feature identity drift")
        if any(
            item.source_position is not None or item.position_group is not PositionGroup.UNKNOWN
            for item in self.candidate.player_components
        ):
            raise RealPlayerContextAuthoritativeBridgeError("position semantics leaked into bridge")
        if any(item.status is FeatureStatus.AVAILABLE for item in self.candidate.player_components):
            raise RealPlayerContextAuthoritativeBridgeError("historical player evidence was invented")
        if tuple(self.authority.items()) != _AUTHORITY:
            raise RealPlayerContextAuthoritativeBridgeError("bridge authority drift")

    def to_dict(self) -> dict[str, Any]:
        iso = lambda value: value.isoformat().replace("+00:00", "Z")
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "bridge_scope": self.bridge_scope,
            "source_pr193_admission_sha256": self.source_pr193_admission_sha256,
            "source_pr194_handoff_sha256": self.source_pr194_handoff_sha256,
            "source_pr194_handoff_size": self.source_pr194_handoff_size,
            "source_raw_sha256": self.source_raw_sha256,
            "source_structure_sha256": self.source_structure_sha256,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "source_observed_at": iso(self.source_observed_at),
            "source_classified_at": iso(self.source_classified_at),
            "source_state_fresh_until": iso(self.source_state_fresh_until),
            "lineage_scalar_pointer": self.lineage_scalar_pointer,
            "lineage_scalar_field": self.lineage_scalar_field,
            "lineage_scalar_value": self.lineage_scalar_value,
            "source_field_review_sha256": self.source_field_review_sha256,
            "source_qualification_sha256": self.source_qualification_sha256,
            "source_policy_sha256": self.source_policy_sha256,
            "source_evaluation_sha256": self.source_evaluation_sha256,
            "source_materialization_sha256": self.source_materialization_sha256,
            "source_materialization_size": self.source_materialization_size,
            "source_candidate_set_sha256": self.source_candidate_set_sha256,
            "source_candidate_set_size": self.source_candidate_set_size,
            "source_candidate_admission_sha256": self.source_candidate_admission_sha256,
            "source_candidate_admission_size": self.source_candidate_admission_size,
            "source_pr65_artifact_sha256": self.source_pr65_artifact_sha256,
            "source_pr65_artifact_size": self.source_pr65_artifact_size,
            "source_pr66_handoff_sha256": self.source_pr66_handoff_sha256,
            "source_pr66_handoff_size": self.source_pr66_handoff_size,
            "source_fixture_intelligence_snapshot_sha256": self.source_fixture_intelligence_snapshot_sha256,
            "source_model_feature_snapshot_sha256": self.source_model_feature_snapshot_sha256,
            "candidate": self.candidate.to_dict(),
            "candidate_sha256": self.candidate_sha256,
            "candidate_size": self.candidate_size,
            "available_feature_ids": list(self.available_feature_ids),
            "authority": dict(self.authority),
        }


@dataclasses.dataclass(frozen=True)
class _RealScalarLineage:
    pr65: ReviewedMatchDetailsFixtureIntelligenceSnapshot
    pr65_bytes: bytes
    pr66: ReviewedMatchDetailsModelFeatureHandoff
    pr66_bytes: bytes
    field_review_bytes: bytes
    qualification_bytes: bytes
    policy_bytes: bytes
    evaluation_bytes: bytes
    materialization_bytes: bytes
    candidate_set_bytes: bytes
    admission_bytes: bytes


def _build_real_scalar_lineage(
    *,
    manifest_bytes: bytes,
    raw_bytes: bytes,
    persisted_receipt_bytes: bytes,
    structure_assessment_bytes: bytes,
) -> _RealScalarLineage:
    try:
        evidence = verify_persisted_match_details_evidence(
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
        )
        evidence_receipt_bytes = canonical_persisted_match_details_evidence_receipt_bytes(evidence)
        if evidence_receipt_bytes != persisted_receipt_bytes:
            raise RealPlayerContextAuthoritativeBridgeError("PR52 persisted receipt replay mismatch")
        assessment = assess_reviewed_match_details_structure(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
        )
        assessment_bytes = canonical_reviewed_match_details_structure_bytes(assessment)
        if assessment_bytes != structure_assessment_bytes:
            raise RealPlayerContextAuthoritativeBridgeError("PR53 structure replay mismatch")
        if (
            evidence.fixture_identifier,
            evidence.source_match_id,
            evidence.kickoff,
            evidence.observed_at,
            evidence.raw_sha256,
            _sha(assessment_bytes),
        ) != (
            PR193_FIXTURE_IDENTIFIER,
            PR193_SOURCE_MATCH_ID,
            PR193_KICKOFF,
            PR193_OBSERVED_AT,
            PR193_RAW_SHA256,
            PR193_STRUCTURE_SHA256,
        ):
            raise RealPlayerContextAuthoritativeBridgeError("PR52/53 exact source identity drift")

        field_decision = MatchDetailsFieldReviewDecision(
            json_pointer=LINEAGE_SCALAR_POINTER,
            expected_kind=JsonValueKind.STRING,
            disposition=FieldReviewDisposition.APPROVED,
            category=IntelligenceCategory.LINEUP,
            field=LINEAGE_SCALAR_FIELD,
            notes=(
                "PR197 reuses the exact PR193-reviewed lineupType='predicted' scalar only "
                "as a same-raw lineage sentinel; it is not a model feature."
            ),
        )
        review = build_reviewed_match_details_field_semantics(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            decisions=(field_decision,),
            reviewed_at=PR193_CLASSIFIED_AT,
            reviewer_reference=LINEAGE_REVIEWER_REFERENCE,
        )
        review_bytes = canonical_reviewed_match_details_field_semantics_bytes(review)

        candidate_bundle = build_reviewed_match_details_unverified_candidates(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
        )
        candidate_bundle_bytes = canonical_reviewed_match_details_unverified_candidate_bundle_bytes(
            candidate_bundle
        )
        fact_bundle = build_reviewed_match_details_unverified_fact_bundle(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            candidate_bundle=candidate_bundle,
            candidate_bundle_bytes=candidate_bundle_bytes,
        )
        fact_bundle_bytes = canonical_reviewed_match_details_unverified_fact_bundle_bytes(fact_bundle)
        if len(fact_bundle.facts) != 1:
            raise RealPlayerContextAuthoritativeBridgeError("lineage scalar must create exactly one fact")
        fact = fact_bundle.facts[0]
        if (
            fact.category is not IntelligenceCategory.LINEUP
            or fact.field != LINEAGE_SCALAR_FIELD
            or fact.value != LINEAGE_SCALAR_VALUE
        ):
            raise RealPlayerContextAuthoritativeBridgeError("lineage scalar semantic/value drift")

        qualification_decision = MatchDetailsFieldEvidenceReviewDecision(
            category=fact.category,
            field=fact.field,
            source_reference=fact.source_reference,
            disposition=FieldEvidenceQualificationDisposition.QUALIFIED,
            rationale=(
                "Exact PR193 review already established the single-observation source "
                "lineupType='predicted' semantic; qualify only that exact fact."
            ),
        )
        qualification = build_reviewed_match_details_field_evidence_qualification(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bundle_bytes,
            decisions=(qualification_decision,),
            reviewed_at=PR193_CLASSIFIED_AT,
            reviewer_reference=LINEAGE_QUALIFICATION_REFERENCE,
        )
        qualification_bytes = canonical_reviewed_match_details_field_evidence_qualification_bytes(
            qualification
        )
        freshness_rule = MatchDetailsFreshnessPolicyRule(
            category=fact.category,
            field=fact.field,
            source_reference=fact.source_reference,
            fresh_until=PR193_CLASSIFIED_AT,
            rationale=(
                "Exact PR193 observation is current only through its classification instant; "
                "no Saturday carry-forward is authorized."
            ),
        )
        policy = build_reviewed_match_details_status_classification_policy(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bundle_bytes,
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            freshness_rules=(freshness_rule,),
            policy_reviewed_at=PR193_CLASSIFIED_AT,
            reviewer_reference=LINEAGE_POLICY_REFERENCE,
        )
        policy_bytes = canonical_reviewed_match_details_status_classification_policy_bytes(policy)
        evaluation = evaluate_reviewed_match_details_status_policy(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bundle_bytes,
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            policy=policy,
            policy_bytes=policy_bytes,
            classified_at=PR193_CLASSIFIED_AT,
        )
        evaluation_bytes = canonical_reviewed_match_details_status_evaluation_bytes(evaluation)
        materialization = materialize_reviewed_match_details_fact_statuses(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bundle_bytes,
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            policy=policy,
            policy_bytes=policy_bytes,
            evaluation=evaluation,
            evaluation_bytes=evaluation_bytes,
        )
        materialization_bytes = canonical_reviewed_match_details_fact_status_materialization_bytes(
            materialization
        )
        if (
            len(materialization.materialized_facts) != 1
            or materialization.materialized_facts[0].status is not IntelligenceFactStatus.SUPPORTED
            or materialization.materialized_facts[0].field != LINEAGE_SCALAR_FIELD
            or materialization.materialized_facts[0].value != LINEAGE_SCALAR_VALUE
        ):
            raise RealPlayerContextAuthoritativeBridgeError(
                "exact scalar lineage did not materialize one SUPPORTED sentinel fact"
            )

        chain_input = ReviewedMatchDetailsMaterializationChainInput(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bundle_bytes,
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            policy=policy,
            policy_bytes=policy_bytes,
            evaluation=evaluation,
            evaluation_bytes=evaluation_bytes,
            materialization=materialization,
            materialization_bytes=materialization_bytes,
        )
        if (
            chain_input.evidence.raw_sha256 != PR193_RAW_SHA256
            or _sha(chain_input.assessment_bytes) != PR193_STRUCTURE_SHA256
        ):
            raise RealPlayerContextAuthoritativeBridgeError(
                "PR65 materialization input is not the exact PR193 raw/PR53 observation"
            )
        materialization_inputs = (chain_input,)
        candidate_set = build_reviewed_match_details_snapshot_candidate_set(
            materialization_inputs=materialization_inputs
        )
        candidate_set_bytes = canonical_reviewed_match_details_snapshot_candidate_set_bytes(
            candidate_set
        )
        admission = admit_reviewed_match_details_snapshot_candidate_set(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            disposition=SnapshotCandidateAdmissionDisposition.ADMITTED,
            completeness_attestation=(
                SnapshotCandidateCompletenessAttestation.NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS
            ),
            reviewed_at=PR193_CLASSIFIED_AT,
            reviewer_reference=LINEAGE_ADMISSION_REFERENCE,
            rationale=(
                "Admit the complete one-member exact scalar lineage set; no subset selection "
                "and no additional model-feature semantics are asserted."
            ),
        )
        admission_bytes = canonical_reviewed_match_details_snapshot_candidate_admission_bytes(
            admission
        )
        pr65 = build_reviewed_match_details_fixture_intelligence_snapshot(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
        )
        pr65_bytes = canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes(pr65)
        if (
            pr65.fixture_identifier != PR193_FIXTURE_IDENTIFIER
            or pr65.source_match_id != PR193_SOURCE_MATCH_ID
            or pr65.kickoff != PR193_KICKOFF
            or pr65.classified_at != PR193_CLASSIFIED_AT
            or pr65.member_count != 1
            or pr65.fact_count != 1
            or len(pr65.snapshot.facts) != 1
            or pr65.snapshot.facts[0].category is not IntelligenceCategory.LINEUP
            or pr65.snapshot.facts[0].field != LINEAGE_SCALAR_FIELD
            or pr65.snapshot.facts[0].value != LINEAGE_SCALAR_VALUE
            or pr65.snapshot.facts[0].status is not IntelligenceFactStatus.SUPPORTED
        ):
            raise RealPlayerContextAuthoritativeBridgeError("PR65 exact scalar snapshot drift")

        pr66 = build_reviewed_match_details_model_feature_handoff(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
            artifact=pr65,
            artifact_bytes=pr65_bytes,
        )
        pr66_bytes = canonical_reviewed_match_details_model_feature_handoff_bytes(pr66)
        if any(
            item.status is not ModelFeatureStatus.MISSING
            for item in pr66.model_feature_snapshot.features
        ):
            raise RealPlayerContextAuthoritativeBridgeError(
                "lineage sentinel must not create any PR31 model feature"
            )
        return _RealScalarLineage(
            pr65=pr65,
            pr65_bytes=pr65_bytes,
            pr66=pr66,
            pr66_bytes=pr66_bytes,
            field_review_bytes=review_bytes,
            qualification_bytes=qualification_bytes,
            policy_bytes=policy_bytes,
            evaluation_bytes=evaluation_bytes,
            materialization_bytes=materialization_bytes,
            candidate_set_bytes=candidate_set_bytes,
            admission_bytes=admission_bytes,
        )
    except RealPlayerContextAuthoritativeBridgeError:
        raise
    except Exception as exc:
        raise RealPlayerContextAuthoritativeBridgeError(
            "exact PR52→PR66 real scalar lineage replay failed"
        ) from exc


def build_reviewed_real_fotmob_authoritative_team_strength_bridge(
    *,
    campaign_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    persisted_receipt_bytes: Any,
    structure_assessment_bytes: Any,
) -> ReviewedRealFotMobAuthoritativeTeamStrengthBridge:
    exact_inputs = (
        campaign_receipt_bytes,
        manifest_bytes,
        raw_bytes,
        persisted_receipt_bytes,
        structure_assessment_bytes,
    )
    if any(type(value) is not bytes or not value for value in exact_inputs):
        raise RealPlayerContextAuthoritativeBridgeError(
            "all PR192 source inputs must be exact non-empty bytes"
        )
    try:
        pr194 = build_reviewed_real_fotmob_team_strength_handoff(
            campaign_receipt_bytes=campaign_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            persisted_receipt_bytes=persisted_receipt_bytes,
            structure_assessment_bytes=structure_assessment_bytes,
        )
        if type(pr194) is not ReviewedRealFotMobTeamStrengthHandoff:
            raise RealPlayerContextAuthoritativeBridgeError("PR194 replay type drift")
        pr194_bytes = canonical_reviewed_real_fotmob_team_strength_handoff_bytes(pr194)
        if _sha(pr194_bytes) != SOURCE_PR194_HANDOFF_SHA256:
            raise RealPlayerContextAuthoritativeBridgeError("exact PR194 canonical identity drift")
        lineage = _build_real_scalar_lineage(
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            persisted_receipt_bytes=persisted_receipt_bytes,
            structure_assessment_bytes=structure_assessment_bytes,
        )
    except RealPlayerContextAuthoritativeBridgeError:
        raise
    except Exception as exc:
        raise RealPlayerContextAuthoritativeBridgeError(
            "PR193/PR194 or PR65/PR66 source replay failed"
        ) from exc

    candidate_bytes = canonical_team_strength_context_candidate_bytes(pr194.candidate)
    return _new(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        bridge_scope=BRIDGE_SCOPE,
        source_pr193_admission_sha256=SOURCE_ADMISSION_SHA256,
        source_pr194_handoff_sha256=_sha(pr194_bytes),
        source_pr194_handoff_size=len(pr194_bytes),
        source_raw_sha256=PR193_RAW_SHA256,
        source_structure_sha256=PR193_STRUCTURE_SHA256,
        fixture_identifier=pr194.fixture_identifier,
        source_match_id=pr194.source_match_id,
        home_team_id=pr194.home_team_id,
        away_team_id=pr194.away_team_id,
        source_observed_at=pr194.source_observed_at,
        source_classified_at=pr194.source_classified_at,
        source_state_fresh_until=pr194.source_state_fresh_until,
        lineage_scalar_pointer=LINEAGE_SCALAR_POINTER,
        lineage_scalar_field=LINEAGE_SCALAR_FIELD,
        lineage_scalar_value=LINEAGE_SCALAR_VALUE,
        source_field_review_sha256=_sha(lineage.field_review_bytes),
        source_qualification_sha256=_sha(lineage.qualification_bytes),
        source_policy_sha256=_sha(lineage.policy_bytes),
        source_evaluation_sha256=_sha(lineage.evaluation_bytes),
        source_materialization_sha256=_sha(lineage.materialization_bytes),
        source_materialization_size=len(lineage.materialization_bytes),
        source_candidate_set_sha256=_sha(lineage.candidate_set_bytes),
        source_candidate_set_size=len(lineage.candidate_set_bytes),
        source_candidate_admission_sha256=_sha(lineage.admission_bytes),
        source_candidate_admission_size=len(lineage.admission_bytes),
        source_pr65_artifact_sha256=_sha(lineage.pr65_bytes),
        source_pr65_artifact_size=len(lineage.pr65_bytes),
        source_pr66_handoff_sha256=_sha(lineage.pr66_bytes),
        source_pr66_handoff_size=len(lineage.pr66_bytes),
        source_fixture_intelligence_snapshot_sha256=lineage.pr65.snapshot_sha256,
        source_model_feature_snapshot_sha256=lineage.pr66.model_feature_snapshot_sha256,
        candidate=pr194.candidate,
        candidate_sha256=_sha(candidate_bytes),
        candidate_size=len(candidate_bytes),
        available_feature_ids=pr194.available_feature_ids,
        authority=types.MappingProxyType(dict(_AUTHORITY)),
    )


def canonical_reviewed_real_fotmob_authoritative_team_strength_bridge_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ReviewedRealFotMobAuthoritativeTeamStrengthBridge:
        raise RealPlayerContextAuthoritativeBridgeError(
            "value must be exact authoritative team-strength bridge"
        )
    canonical_team_strength_context_candidate_bytes(value.candidate)
    value.__post_init__()
    return _canonical(value.to_dict())


def sha256_reviewed_real_fotmob_authoritative_team_strength_bridge(value: Any) -> str:
    return _sha(canonical_reviewed_real_fotmob_authoritative_team_strength_bridge_bytes(value))


def revalidate_reviewed_real_fotmob_authoritative_team_strength_bridge(
    *,
    campaign_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    persisted_receipt_bytes: Any,
    structure_assessment_bytes: Any,
    bridge: Any,
    bridge_bytes: Any,
) -> ReviewedRealFotMobAuthoritativeTeamStrengthBridge:
    if (
        type(bridge) is not ReviewedRealFotMobAuthoritativeTeamStrengthBridge
        or type(bridge_bytes) is not bytes
    ):
        raise RealPlayerContextAuthoritativeBridgeError(
            "bridge/object bytes must be exact immutable values"
        )
    supplied = canonical_reviewed_real_fotmob_authoritative_team_strength_bridge_bytes(bridge)
    rebuilt = build_reviewed_real_fotmob_authoritative_team_strength_bridge(
        campaign_receipt_bytes=campaign_receipt_bytes,
        manifest_bytes=manifest_bytes,
        raw_bytes=raw_bytes,
        persisted_receipt_bytes=persisted_receipt_bytes,
        structure_assessment_bytes=structure_assessment_bytes,
    )
    exact = canonical_reviewed_real_fotmob_authoritative_team_strength_bridge_bytes(rebuilt)
    if supplied != exact or bridge_bytes != exact:
        raise RealPlayerContextAuthoritativeBridgeError(
            "authoritative bridge differs from exact full PR192→PR66 replay"
        )
    return rebuilt


__all__ = [
    "BRIDGE_SCOPE",
    "DATASET_NAME",
    "LINEAGE_SCALAR_FIELD",
    "LINEAGE_SCALAR_POINTER",
    "LINEAGE_SCALAR_VALUE",
    "RealPlayerContextAuthoritativeBridgeError",
    "ReviewedRealFotMobAuthoritativeTeamStrengthBridge",
    "SCHEMA_VERSION",
    "build_reviewed_real_fotmob_authoritative_team_strength_bridge",
    "canonical_reviewed_real_fotmob_authoritative_team_strength_bridge_bytes",
    "revalidate_reviewed_real_fotmob_authoritative_team_strength_bridge",
    "sha256_reviewed_real_fotmob_authoritative_team_strength_bridge",
]
