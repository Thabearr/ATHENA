"""Exact real FotMob player-context -> authoritative team-strength bridge.

This source-specific boundary closes the gap left deliberately by PR194.  It
replays the exact PR192 bytes through PR193/PR194, independently establishes a
PR52->PR66 Fixture Intelligence/model-feature lineage from the *same* raw
observation, and only then grants the PR191-style team-strength feature
boundary for that exact observation.

It does not widen the generic PR191 array schema to fit one provider response,
does not project Thursday player state forward to Saturday, and grants no xG,
probability, pricing, selection, production, or BET authority.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from typing import Any, Mapping

from domain.fixture_intelligence import IntelligenceCategory, IntelligenceFactStatus
from domain.fixture_model_features import ModelFeatureStatus
from domain.fotmob_real_player_context_array_admission import (
    CLASSIFIED_AT as PR193_CLASSIFIED_AT,
    FIXTURE_IDENTIFIER as PR193_FIXTURE_IDENTIFIER,
    KICKOFF as PR193_KICKOFF,
    RAW_SHA256 as PR193_RAW_SHA256,
    SOURCE_MATCH_ID as PR193_SOURCE_MATCH_ID,
    STRUCTURE_SHA256 as PR193_STRUCTURE_SHA256,
)
from domain.fotmob_real_player_context_team_strength_handoff import (
    EXPECTED_CANDIDATE_SHA256 as PR194_CANDIDATE_SHA256,
    SOURCE_ADMISSION_SHA256 as PR193_ADMISSION_SHA256,
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
    build_reviewed_match_details_fixture_intelligence_snapshot,
    canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes,
)
from domain.fotmob_reviewed_match_details_model_feature_handoff import (
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
    evaluate_reviewed_match_details_status_policy,
    canonical_reviewed_match_details_status_evaluation_bytes,
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
from domain.fotmob_team_strength_fixture_intelligence import FeatureStatus


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-real-player-context-authoritative-team-strength-v1"
AUTHORITY_SCOPE = (
    "EXACT_PR192_PR193_PR194_WITH_SAME_RAW_REVALIDATED_PR52_TO_PR66_LINEAGE_ONLY"
)
LINEAGE_FIELD_POINTER = "/content/lineup/lineupType"
LINEAGE_FIELD_NAME = "lineup_type"
LINEAGE_SOURCE_VALUE = "predicted"
REVIEWER_REFERENCE = "ATHENA-PR197-EXACT-REAL-PLAYER-CONTEXT-AUTHORITY"

_EXPECTED_AVAILABLE_FEATURES = {
    "away_unavailable_player_count": 5.0,
    "home_unavailable_player_count": 1.0,
}
_EXPECTED_AVAILABLE_FEATURE_IDS = tuple(sorted(_EXPECTED_AVAILABLE_FEATURES))
_AUTHORITY = tuple(
    sorted(
        {
            "bet_authorized": False,
            "bench_semantics_used": False,
            "exact_observation_team_strength_feature_authorized": True,
            "historical_player_evidence_used": False,
            "position_semantics_used": False,
            "pricing_authorized": False,
            "probability_adjustment_authorized": False,
            "probability_inference_authorized": False,
            "production_approval_authorized": False,
            "prospective_reuse_after_source_freshness_authorized": False,
            "selection_authorized": False,
            "source_wide_team_strength_authorized": False,
            "team_strength_feature_authorized": True,
        }.items()
    )
)


class RealPlayerContextAuthoritativeTeamStrengthError(ValueError):
    pass


def _sha(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise RealPlayerContextAuthoritativeTeamStrengthError("hash input must be exact bytes")
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
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "authoritative bridge canonicalization failed"
        ) from exc


def _new(**values: Any) -> "ReviewedRealFotMobAuthoritativeTeamStrengthContext":
    obj = object.__new__(ReviewedRealFotMobAuthoritativeTeamStrengthContext)
    expected = {
        field.name
        for field in dataclasses.fields(ReviewedRealFotMobAuthoritativeTeamStrengthContext)
    }
    if set(values) != expected:
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "internal authoritative bridge field drift"
        )
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    obj.__post_init__()
    return obj


@dataclasses.dataclass(frozen=True, init=False)
class ReviewedRealFotMobAuthoritativeTeamStrengthContext:
    schema_version: int
    dataset_name: str
    authority_scope: str
    fixture_identifier: str
    source_match_id: str
    source_raw_sha256: str
    source_structure_sha256: str
    source_pr193_admission_sha256: str
    source_pr194_handoff_sha256: str
    source_pr194_candidate_sha256: str
    source_pr65_artifact_sha256: str
    source_pr65_artifact_size: int
    source_pr66_handoff_sha256: str
    source_pr66_handoff_size: int
    source_fixture_intelligence_snapshot_sha256: str
    source_model_feature_snapshot_sha256: str
    source_state_fresh_until: Any
    candidate: Any
    candidate_sha256: str
    candidate_size: int
    authorized_feature_ids: tuple[str, ...]
    authority: Mapping[str, bool]

    def __init__(self, *_: Any, **__: Any) -> None:
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "authoritative context can only be created by exact source replay"
        )

    def __post_init__(self) -> None:
        if (
            self.schema_version,
            self.dataset_name,
            self.authority_scope,
        ) != (SCHEMA_VERSION, DATASET_NAME, AUTHORITY_SCOPE):
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "authoritative bridge identity drift"
            )
        if (
            self.fixture_identifier != PR193_FIXTURE_IDENTIFIER
            or self.source_match_id != PR193_SOURCE_MATCH_ID
            or self.source_raw_sha256 != PR193_RAW_SHA256
            or self.source_structure_sha256 != PR193_STRUCTURE_SHA256
            or self.source_pr193_admission_sha256 != PR193_ADMISSION_SHA256
            or self.source_pr194_candidate_sha256 != PR194_CANDIDATE_SHA256
        ):
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "exact PR193/PR194 source identity drift"
            )
        for label in (
            "source_pr194_handoff_sha256",
            "source_pr65_artifact_sha256",
            "source_pr66_handoff_sha256",
            "source_fixture_intelligence_snapshot_sha256",
            "source_model_feature_snapshot_sha256",
            "candidate_sha256",
        ):
            value = getattr(self, label)
            if (
                type(value) is not str
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise RealPlayerContextAuthoritativeTeamStrengthError(
                    f"{label} must be exact lowercase SHA-256"
                )
        if (
            type(self.source_pr65_artifact_size) is not int
            or self.source_pr65_artifact_size <= 0
            or type(self.source_pr66_handoff_size) is not int
            or self.source_pr66_handoff_size <= 0
            or type(self.candidate_size) is not int
            or self.candidate_size <= 0
        ):
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "authoritative byte sizes must be positive integers"
            )
        if self.source_state_fresh_until != PR193_CLASSIFIED_AT:
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "source freshness boundary drift"
            )
        candidate_bytes = __import__(
            "domain.fotmob_team_strength_fixture_intelligence",
            fromlist=["canonical_team_strength_context_candidate_bytes"],
        ).canonical_team_strength_context_candidate_bytes(self.candidate)
        if (
            _sha(candidate_bytes) != PR194_CANDIDATE_SHA256
            or self.candidate_sha256 != PR194_CANDIDATE_SHA256
            or self.candidate_size != len(candidate_bytes)
        ):
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "nested PR194 candidate identity drift"
            )
        if tuple(self.authorized_feature_ids) != _EXPECTED_AVAILABLE_FEATURE_IDS:
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "authorized feature set exceeds exact reviewed semantics"
            )
        available = {
            item.feature_id.value: item.value
            for item in self.candidate.features
            if item.status is FeatureStatus.AVAILABLE
        }
        if available != _EXPECTED_AVAILABLE_FEATURES:
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "candidate available features drift from exact reviewed observation"
            )
        if any(value for _, value in self.candidate.safety):
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "nested PR190 candidate safety must remain all false"
            )
        if tuple(self.authority.items()) != _AUTHORITY:
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "authoritative bridge safety/authority drift"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "authority_scope": self.authority_scope,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "source_raw_sha256": self.source_raw_sha256,
            "source_structure_sha256": self.source_structure_sha256,
            "source_pr193_admission_sha256": self.source_pr193_admission_sha256,
            "source_pr194_handoff_sha256": self.source_pr194_handoff_sha256,
            "source_pr194_candidate_sha256": self.source_pr194_candidate_sha256,
            "source_pr65_artifact_sha256": self.source_pr65_artifact_sha256,
            "source_pr65_artifact_size": self.source_pr65_artifact_size,
            "source_pr66_handoff_sha256": self.source_pr66_handoff_sha256,
            "source_pr66_handoff_size": self.source_pr66_handoff_size,
            "source_fixture_intelligence_snapshot_sha256": self.source_fixture_intelligence_snapshot_sha256,
            "source_model_feature_snapshot_sha256": self.source_model_feature_snapshot_sha256,
            "source_state_fresh_until": self.source_state_fresh_until.isoformat().replace(
                "+00:00", "Z"
            ),
            "candidate": self.candidate.to_dict(),
            "candidate_sha256": self.candidate_sha256,
            "candidate_size": self.candidate_size,
            "authorized_feature_ids": list(self.authorized_feature_ids),
            "authority": dict(self.authority),
        }


def _build_same_raw_pr65_pr66(
    *, manifest_bytes: bytes, raw_bytes: bytes, persisted_receipt_bytes: bytes,
    structure_assessment_bytes: bytes,
):
    try:
        evidence = verify_persisted_match_details_evidence(
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
        )
        exact_receipt_bytes = canonical_persisted_match_details_evidence_receipt_bytes(
            evidence
        )
        if exact_receipt_bytes != persisted_receipt_bytes:
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "exact PR52 receipt bytes differ from preserved source artifact"
            )
        structure = assess_reviewed_match_details_structure(
            evidence=evidence,
            evidence_receipt_bytes=exact_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
        )
        exact_structure_bytes = canonical_reviewed_match_details_structure_bytes(structure)
        if exact_structure_bytes != structure_assessment_bytes:
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "exact PR53 structure bytes differ from preserved source artifact"
            )
        if (
            evidence.fixture_identifier,
            evidence.source_match_id,
            evidence.kickoff,
            evidence.raw_sha256,
            _sha(exact_structure_bytes),
        ) != (
            PR193_FIXTURE_IDENTIFIER,
            PR193_SOURCE_MATCH_ID,
            PR193_KICKOFF,
            PR193_RAW_SHA256,
            PR193_STRUCTURE_SHA256,
        ):
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "PR52/PR53 exact real observation identity drift"
            )

        semantic_review = build_reviewed_match_details_field_semantics(
            evidence=evidence,
            evidence_receipt_bytes=exact_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=structure,
            assessment_bytes=exact_structure_bytes,
            decisions=(
                MatchDetailsFieldReviewDecision(
                    json_pointer=LINEAGE_FIELD_POINTER,
                    expected_kind=JsonValueKind.STRING,
                    disposition=FieldReviewDisposition.APPROVED,
                    category=IntelligenceCategory.LINEUP,
                    field=LINEAGE_FIELD_NAME,
                    notes=(
                        "PR197 exact-observation bridge only: PR193 independently "
                        "reviewed content.lineup.lineupType='predicted'."
                    ),
                ),
            ),
            reviewed_at=PR193_CLASSIFIED_AT,
            reviewer_reference=REVIEWER_REFERENCE,
        )
        semantic_review_bytes = canonical_reviewed_match_details_field_semantics_bytes(
            semantic_review
        )
        candidate_bundle = build_reviewed_match_details_unverified_candidates(
            evidence=evidence,
            evidence_receipt_bytes=exact_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=structure,
            assessment_bytes=exact_structure_bytes,
            review=semantic_review,
            review_bytes=semantic_review_bytes,
        )
        candidate_bundle_bytes = canonical_reviewed_match_details_unverified_candidate_bundle_bytes(
            candidate_bundle
        )
        fact_bundle = build_reviewed_match_details_unverified_fact_bundle(
            evidence=evidence,
            evidence_receipt_bytes=exact_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=structure,
            assessment_bytes=exact_structure_bytes,
            review=semantic_review,
            review_bytes=semantic_review_bytes,
            candidate_bundle=candidate_bundle,
            candidate_bundle_bytes=candidate_bundle_bytes,
        )
        fact_bundle_bytes = canonical_reviewed_match_details_unverified_fact_bundle_bytes(
            fact_bundle
        )
        if len(fact_bundle.facts) != 1:
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "same-raw lineage must contain exactly one reviewed scalar fact"
            )
        fact = fact_bundle.facts[0]
        if (
            fact.category is not IntelligenceCategory.LINEUP
            or fact.field != LINEAGE_FIELD_NAME
            or fact.value != LINEAGE_SOURCE_VALUE
            or fact.status is not IntelligenceFactStatus.UNVERIFIED
            or fact.evidence_sha256 != PR193_RAW_SHA256
        ):
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                "same-raw lineage scalar differs from exact PR193 observation"
            )
        qualification = build_reviewed_match_details_field_evidence_qualification(
            evidence=evidence,
            evidence_receipt_bytes=exact_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=structure,
            assessment_bytes=exact_structure_bytes,
            review=semantic_review,
            review_bytes=semantic_review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bundle_bytes,
            decisions=(
                MatchDetailsFieldEvidenceReviewDecision(
                    category=fact.category,
                    field=fact.field,
                    source_reference=fact.source_reference,
                    disposition=FieldEvidenceQualificationDisposition.QUALIFIED,
                    rationale=(
                        "Exact PR193 observation only; no source-wide FotMob "
                        "qualification is implied."
                    ),
                ),
            ),
            reviewed_at=PR193_CLASSIFIED_AT,
            reviewer_reference=REVIEWER_REFERENCE,
        )
        qualification_bytes = canonical_reviewed_match_details_field_evidence_qualification_bytes(
            qualification
        )
        policy = build_reviewed_match_details_status_classification_policy(
            evidence=evidence,
            evidence_receipt_bytes=exact_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=structure,
            assessment_bytes=exact_structure_bytes,
            review=semantic_review,
            review_bytes=semantic_review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bundle_bytes,
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            freshness_rules=(
                MatchDetailsFreshnessPolicyRule(
                    category=fact.category,
                    field=fact.field,
                    source_reference=fact.source_reference,
                    fresh_until=PR193_CLASSIFIED_AT,
                    rationale=(
                        "Exact player-context state is fresh only through the PR193 "
                        "classification instant."
                    ),
                ),
            ),
            policy_reviewed_at=PR193_CLASSIFIED_AT,
            reviewer_reference=REVIEWER_REFERENCE,
        )
        policy_bytes = canonical_reviewed_match_details_status_classification_policy_bytes(
            policy
        )
        evaluation = evaluate_reviewed_match_details_status_policy(
            evidence=evidence,
            evidence_receipt_bytes=exact_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=structure,
            assessment_bytes=exact_structure_bytes,
            review=semantic_review,
            review_bytes=semantic_review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bundle_bytes,
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            policy=policy,
            policy_bytes=policy_bytes,
            classified_at=PR193_CLASSIFIED_AT,
        )
        evaluation_bytes = canonical_reviewed_match_details_status_evaluation_bytes(
            evaluation
        )
        materialization = materialize_reviewed_match_details_fact_statuses(
            evidence=evidence,
            evidence_receipt_bytes=exact_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=structure,
            assessment_bytes=exact_structure_bytes,
            review=semantic_review,
            review_bytes=semantic_review_bytes,
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
        chain = ReviewedMatchDetailsMaterializationChainInput(
            evidence=evidence,
            evidence_receipt_bytes=exact_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=structure,
            assessment_bytes=exact_structure_bytes,
            review=semantic_review,
            review_bytes=semantic_review_bytes,
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
        candidate_set = build_reviewed_match_details_snapshot_candidate_set(
            materialization_inputs=(chain,)
        )
        candidate_set_bytes = canonical_reviewed_match_details_snapshot_candidate_set_bytes(
            candidate_set
        )
        admission = admit_reviewed_match_details_snapshot_candidate_set(
            materialization_inputs=(chain,),
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            disposition=SnapshotCandidateAdmissionDisposition.ADMITTED,
            completeness_attestation=(
                SnapshotCandidateCompletenessAttestation.NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS
            ),
            reviewed_at=PR193_CLASSIFIED_AT,
            reviewer_reference=REVIEWER_REFERENCE,
            rationale=(
                "Admit the one exact same-raw LINEUP scalar materialization solely "
                "to establish PR65/PR66 ancestry for the PR193/PR194 observation."
            ),
        )
        admission_bytes = canonical_reviewed_match_details_snapshot_candidate_admission_bytes(
            admission
        )
        pr65 = build_reviewed_match_details_fixture_intelligence_snapshot(
            materialization_inputs=(chain,),
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
        )
        pr65_bytes = canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes(pr65)
        pr66 = build_reviewed_match_details_model_feature_handoff(
            materialization_inputs=(chain,),
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
            artifact=pr65,
            artifact_bytes=pr65_bytes,
        )
        pr66_bytes = canonical_reviewed_match_details_model_feature_handoff_bytes(pr66)
    except RealPlayerContextAuthoritativeTeamStrengthError:
        raise
    except Exception as exc:
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "same-raw PR52->PR66 authority lineage failed exact replay"
        ) from exc

    if (
        pr65.fixture_identifier,
        pr65.source_match_id,
        pr65.kickoff,
        pr65.classified_at,
    ) != (
        PR193_FIXTURE_IDENTIFIER,
        PR193_SOURCE_MATCH_ID,
        PR193_KICKOFF,
        PR193_CLASSIFIED_AT,
    ):
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "PR65 fixture/source/kickoff/as-of identity drift"
        )
    if (
        pr66.fixture_identifier,
        pr66.source_match_id,
        pr66.kickoff,
        pr66.as_of,
    ) != (
        PR193_FIXTURE_IDENTIFIER,
        PR193_SOURCE_MATCH_ID,
        PR193_KICKOFF,
        PR193_CLASSIFIED_AT,
    ):
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "PR66 fixture/source/kickoff/as-of identity drift"
        )
    if len(pr65.snapshot.facts) != 1:
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "PR65 same-raw snapshot must contain exactly one lineage fact"
        )
    admitted_fact = pr65.snapshot.facts[0]
    if (
        admitted_fact.category is not IntelligenceCategory.LINEUP
        or admitted_fact.field != LINEAGE_FIELD_NAME
        or admitted_fact.value != LINEAGE_SOURCE_VALUE
        or admitted_fact.status is not IntelligenceFactStatus.SUPPORTED
        or admitted_fact.evidence_sha256 != PR193_RAW_SHA256
    ):
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "PR65 did not preserve exact same-raw reviewed LINEUP fact"
        )
    if any(
        item.status is not ModelFeatureStatus.MISSING
        for item in pr66.model_feature_snapshot.features
    ):
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "PR66 must not invent generic model features from lineup_type"
        )
    if (
        chain.evidence.raw_sha256 != PR193_RAW_SHA256
        or _sha(chain.assessment_bytes) != PR193_STRUCTURE_SHA256
    ):
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "admitted PR65 materialization is not the exact PR193 raw/PR53 observation"
        )
    return pr65, pr65_bytes, pr66, pr66_bytes


def build_reviewed_real_fotmob_authoritative_team_strength_context(
    *, campaign_receipt_bytes: Any, manifest_bytes: Any, raw_bytes: Any,
    persisted_receipt_bytes: Any, structure_assessment_bytes: Any,
) -> ReviewedRealFotMobAuthoritativeTeamStrengthContext:
    for label, value in (
        ("campaign_receipt_bytes", campaign_receipt_bytes),
        ("manifest_bytes", manifest_bytes),
        ("raw_bytes", raw_bytes),
        ("persisted_receipt_bytes", persisted_receipt_bytes),
        ("structure_assessment_bytes", structure_assessment_bytes),
    ):
        if type(value) is not bytes or not value:
            raise RealPlayerContextAuthoritativeTeamStrengthError(
                f"{label} must be exact nonempty immutable bytes"
            )
    try:
        pr194 = build_reviewed_real_fotmob_team_strength_handoff(
            campaign_receipt_bytes=campaign_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            persisted_receipt_bytes=persisted_receipt_bytes,
            structure_assessment_bytes=structure_assessment_bytes,
        )
        pr194_bytes = canonical_reviewed_real_fotmob_team_strength_handoff_bytes(pr194)
    except Exception as exc:
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "PR193/PR194 exact source replay failed"
        ) from exc
    if type(pr194) is not ReviewedRealFotMobTeamStrengthHandoff:
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "PR194 replay returned wrong exact type"
        )
    if (
        pr194.fixture_identifier != PR193_FIXTURE_IDENTIFIER
        or pr194.source_match_id != PR193_SOURCE_MATCH_ID
        or pr194.source_raw_sha256 != PR193_RAW_SHA256
        or pr194.candidate_sha256 != PR194_CANDIDATE_SHA256
        or dict(pr194.authority).get("team_strength_feature_authorized") is not False
    ):
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "PR194 candidate/source authority boundary drift"
        )

    pr65, pr65_bytes, pr66, pr66_bytes = _build_same_raw_pr65_pr66(
        manifest_bytes=manifest_bytes,
        raw_bytes=raw_bytes,
        persisted_receipt_bytes=persisted_receipt_bytes,
        structure_assessment_bytes=structure_assessment_bytes,
    )
    candidate = pr194.candidate
    candidate_bytes = __import__(
        "domain.fotmob_team_strength_fixture_intelligence",
        fromlist=["canonical_team_strength_context_candidate_bytes"],
    ).canonical_team_strength_context_candidate_bytes(candidate)
    return _new(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        authority_scope=AUTHORITY_SCOPE,
        fixture_identifier=PR193_FIXTURE_IDENTIFIER,
        source_match_id=PR193_SOURCE_MATCH_ID,
        source_raw_sha256=PR193_RAW_SHA256,
        source_structure_sha256=PR193_STRUCTURE_SHA256,
        source_pr193_admission_sha256=PR193_ADMISSION_SHA256,
        source_pr194_handoff_sha256=_sha(pr194_bytes),
        source_pr194_candidate_sha256=PR194_CANDIDATE_SHA256,
        source_pr65_artifact_sha256=_sha(pr65_bytes),
        source_pr65_artifact_size=len(pr65_bytes),
        source_pr66_handoff_sha256=_sha(pr66_bytes),
        source_pr66_handoff_size=len(pr66_bytes),
        source_fixture_intelligence_snapshot_sha256=pr65.snapshot_sha256,
        source_model_feature_snapshot_sha256=pr66.model_feature_snapshot_sha256,
        source_state_fresh_until=PR193_CLASSIFIED_AT,
        candidate=candidate,
        candidate_sha256=PR194_CANDIDATE_SHA256,
        candidate_size=len(candidate_bytes),
        authorized_feature_ids=_EXPECTED_AVAILABLE_FEATURE_IDS,
        authority=types.MappingProxyType(dict(_AUTHORITY)),
    )


def canonical_reviewed_real_fotmob_authoritative_team_strength_context_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ReviewedRealFotMobAuthoritativeTeamStrengthContext:
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "value must be exact authoritative team-strength context"
        )
    value.__post_init__()
    return _canonical(value.to_dict())


def sha256_reviewed_real_fotmob_authoritative_team_strength_context(value: Any) -> str:
    return _sha(canonical_reviewed_real_fotmob_authoritative_team_strength_context_bytes(value))


def revalidate_reviewed_real_fotmob_authoritative_team_strength_context(
    *, campaign_receipt_bytes: Any, manifest_bytes: Any, raw_bytes: Any,
    persisted_receipt_bytes: Any, structure_assessment_bytes: Any,
    context: Any, context_bytes: Any,
) -> ReviewedRealFotMobAuthoritativeTeamStrengthContext:
    if (
        type(context) is not ReviewedRealFotMobAuthoritativeTeamStrengthContext
        or type(context_bytes) is not bytes
    ):
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "context/object bytes must be exact immutable authoritative values"
        )
    supplied = canonical_reviewed_real_fotmob_authoritative_team_strength_context_bytes(
        context
    )
    rebuilt = build_reviewed_real_fotmob_authoritative_team_strength_context(
        campaign_receipt_bytes=campaign_receipt_bytes,
        manifest_bytes=manifest_bytes,
        raw_bytes=raw_bytes,
        persisted_receipt_bytes=persisted_receipt_bytes,
        structure_assessment_bytes=structure_assessment_bytes,
    )
    exact = canonical_reviewed_real_fotmob_authoritative_team_strength_context_bytes(
        rebuilt
    )
    if supplied != exact or context_bytes != exact:
        raise RealPlayerContextAuthoritativeTeamStrengthError(
            "authoritative team-strength context differs from exact full replay"
        )
    return rebuilt


__all__ = [
    "AUTHORITY_SCOPE",
    "DATASET_NAME",
    "LINEAGE_FIELD_NAME",
    "LINEAGE_FIELD_POINTER",
    "REVIEWER_REFERENCE",
    "RealPlayerContextAuthoritativeTeamStrengthError",
    "ReviewedRealFotMobAuthoritativeTeamStrengthContext",
    "SCHEMA_VERSION",
    "build_reviewed_real_fotmob_authoritative_team_strength_context",
    "canonical_reviewed_real_fotmob_authoritative_team_strength_context_bytes",
    "revalidate_reviewed_real_fotmob_authoritative_team_strength_context",
    "sha256_reviewed_real_fotmob_authoritative_team_strength_context",
]
