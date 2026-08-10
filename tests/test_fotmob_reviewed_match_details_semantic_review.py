from __future__ import annotations

import dataclasses
import datetime
import importlib.util
from pathlib import Path

import pytest

from domain.fixture_intelligence import IntelligenceCategory, SourceRole
from domain.fotmob_reviewed_match_details_persisted_evidence import (
    canonical_persisted_match_details_evidence_receipt_bytes,
    verify_persisted_match_details_evidence,
)
from domain.fotmob_reviewed_match_details_structure import (
    JsonValueKind,
    assess_reviewed_match_details_structure,
    canonical_reviewed_match_details_structure_bytes,
)
from domain.fotmob_reviewed_match_details_semantic_review import (
    FotMobReviewedMatchDetailsSemanticReviewError,
    ReviewedMatchDetailsFieldDecision,
    SemanticReviewDisposition,
    build_reviewed_match_details_semantic_review,
    canonical_reviewed_match_details_semantic_review_bytes,
    sha256_reviewed_match_details_semantic_review,
)

UTC = datetime.timezone.utc
REVIEWED_AT = datetime.datetime(2026, 8, 10, 10, 5, tzinfo=UTC)


def _pr52_manifest(raw: bytes) -> bytes:
    helper_path = Path(__file__).with_name(
        "test_fotmob_reviewed_match_details_persisted_evidence.py"
    )
    spec = importlib.util.spec_from_file_location("_athena_pr52_semantic_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #52 test helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._manifest_bytes(module._payload(raw))


def _chain(raw: bytes):
    manifest = _pr52_manifest(raw)
    evidence = verify_persisted_match_details_evidence(
        manifest_bytes=manifest,
        raw_bytes=raw,
    )
    evidence_receipt = canonical_persisted_match_details_evidence_receipt_bytes(evidence)
    structure = assess_reviewed_match_details_structure(
        evidence=evidence,
        evidence_receipt_bytes=evidence_receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
    )
    structure_bytes = canonical_reviewed_match_details_structure_bytes(structure)
    return evidence, evidence_receipt, manifest, structure, structure_bytes


def _approved(
    pointer: str = "/general/homeTeam/id",
    kinds: tuple[JsonValueKind, ...] = (JsonValueKind.INTEGER,),
) -> ReviewedMatchDetailsFieldDecision:
    return ReviewedMatchDetailsFieldDecision(
        json_pointer=pointer,
        observed_kinds=kinds,
        disposition=SemanticReviewDisposition.APPROVED,
        category=IntelligenceCategory.FIXTURE_CONTEXT,
        logical_field="home_team_source_id",
        source_role=SourceRole.PRIMARY_FOOTBALL_CONTEXT,
        rationale="Synthetic review fixture: this exact path is approved for the named logical field.",
    )


def _rejected(pointer: str = "/noise") -> ReviewedMatchDetailsFieldDecision:
    return ReviewedMatchDetailsFieldDecision(
        json_pointer=pointer,
        observed_kinds=(JsonValueKind.STRING,),
        disposition=SemanticReviewDisposition.REJECTED,
        category=None,
        logical_field=None,
        source_role=None,
        rationale="Synthetic review fixture: this path is explicitly rejected.",
    )


def _build(raw: bytes = b'{"general":{"homeTeam":{"id":1}},"noise":"x"}'):
    evidence, evidence_receipt, manifest, structure, structure_bytes = _chain(raw)
    review = build_reviewed_match_details_semantic_review(
        structure=structure,
        structure_bytes=structure_bytes,
        evidence=evidence,
        evidence_receipt_bytes=evidence_receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
        decisions=(_rejected(), _approved()),
        reviewed_at=REVIEWED_AT,
        reviewer_reference="ATHENA-SEMANTIC-REVIEW-TEST",
        notes="Synthetic contract test only; no real FotMob field meaning is asserted.",
    )
    return review, evidence, evidence_receipt, manifest, structure, structure_bytes


def test_review_is_exact_human_decision_contract_not_fact_creation() -> None:
    review, *_ = _build()
    assert tuple(item.json_pointer for item in review.decisions) == (
        "/general/homeTeam/id",
        "/noise",
    )
    approved = review.decisions[0]
    assert approved.disposition is SemanticReviewDisposition.APPROVED
    assert approved.category is IntelligenceCategory.FIXTURE_CONTEXT
    assert approved.logical_field == "home_team_source_id"
    assert approved.source_role is SourceRole.PRIMARY_FOOTBALL_CONTEXT
    assert review.decisions[1].disposition is SemanticReviewDisposition.REJECTED
    assert all(value is False for value in review.safety.values())

    canonical = canonical_reviewed_match_details_semantic_review_bytes(review)
    assert canonical.endswith(b"\n")
    assert len(sha256_reviewed_match_details_semantic_review(review)) == 64


def test_exact_pr53_structure_bytes_and_evidence_chain_are_required() -> None:
    raw = b'{"general":{"homeTeam":{"id":1}},"noise":"x"}'
    review, evidence, evidence_receipt, manifest, structure, structure_bytes = _build(raw)
    del review

    with pytest.raises(
        FotMobReviewedMatchDetailsSemanticReviewError,
        match="exact canonical PR #53",
    ):
        build_reviewed_match_details_semantic_review(
            structure=structure,
            structure_bytes=structure_bytes + b"\n",
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            decisions=(_approved(),),
            reviewed_at=REVIEWED_AT,
            reviewer_reference="reviewer",
        )

    with pytest.raises(
        FotMobReviewedMatchDetailsSemanticReviewError,
        match="PR #53 structure",
    ):
        build_reviewed_match_details_semantic_review(
            structure=structure,
            structure_bytes=structure_bytes,
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt,
            manifest_bytes=manifest,
            raw_bytes=raw + b" ",
            decisions=(_approved(),),
            reviewed_at=REVIEWED_AT,
            reviewer_reference="reviewer",
        )


def test_forced_pr53_object_mutation_cannot_be_silently_repaired() -> None:
    raw = b'{"general":{"homeTeam":{"id":1}},"noise":"x"}'
    _, evidence, evidence_receipt, manifest, structure, structure_bytes = _build(raw)
    object.__setattr__(structure, "raw_sha256", "f" * 64)
    with pytest.raises(FotMobReviewedMatchDetailsSemanticReviewError):
        build_reviewed_match_details_semantic_review(
            structure=structure,
            structure_bytes=structure_bytes,
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            decisions=(_approved(),),
            reviewed_at=REVIEWED_AT,
            reviewer_reference="reviewer",
        )


def test_absent_path_and_observed_kind_drift_fail_closed() -> None:
    raw = b'{"general":{"homeTeam":{"id":1}},"noise":"x"}'
    _, evidence, evidence_receipt, manifest, structure, structure_bytes = _build(raw)

    absent = _approved(pointer="/general/awayTeam/id")
    with pytest.raises(FotMobReviewedMatchDetailsSemanticReviewError, match="absent from PR #53"):
        build_reviewed_match_details_semantic_review(
            structure=structure,
            structure_bytes=structure_bytes,
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            decisions=(absent,),
            reviewed_at=REVIEWED_AT,
            reviewer_reference="reviewer",
        )

    wrong_kind = _approved(kinds=(JsonValueKind.STRING,))
    with pytest.raises(FotMobReviewedMatchDetailsSemanticReviewError, match="observed kind mismatch"):
        build_reviewed_match_details_semantic_review(
            structure=structure,
            structure_bytes=structure_bytes,
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            decisions=(wrong_kind,),
            reviewed_at=REVIEWED_AT,
            reviewer_reference="reviewer",
        )


def test_approval_and_rejection_metadata_are_fail_closed() -> None:
    with pytest.raises(FotMobReviewedMatchDetailsSemanticReviewError, match="requires IntelligenceCategory"):
        ReviewedMatchDetailsFieldDecision(
            json_pointer="/x",
            observed_kinds=(JsonValueKind.STRING,),
            disposition=SemanticReviewDisposition.APPROVED,
            category=None,
            logical_field="x",
            source_role=SourceRole.PRIMARY_FOOTBALL_CONTEXT,
            rationale="reason",
        )

    with pytest.raises(FotMobReviewedMatchDetailsSemanticReviewError, match="PRIMARY_FOOTBALL_CONTEXT"):
        ReviewedMatchDetailsFieldDecision(
            json_pointer="/x",
            observed_kinds=(JsonValueKind.STRING,),
            disposition=SemanticReviewDisposition.APPROVED,
            category=IntelligenceCategory.FORM,
            logical_field="x",
            source_role=SourceRole.DISCOVERY_ONLY,
            rationale="reason",
        )

    with pytest.raises(FotMobReviewedMatchDetailsSemanticReviewError, match="must not carry"):
        ReviewedMatchDetailsFieldDecision(
            json_pointer="/x",
            observed_kinds=(JsonValueKind.STRING,),
            disposition=SemanticReviewDisposition.REJECTED,
            category=IntelligenceCategory.FORM,
            logical_field=None,
            source_role=None,
            rationale="reason",
        )


def test_duplicate_pointer_review_and_review_time_fail_closed() -> None:
    raw = b'{"general":{"homeTeam":{"id":1}},"noise":"x"}'
    _, evidence, evidence_receipt, manifest, structure, structure_bytes = _build(raw)
    with pytest.raises(FotMobReviewedMatchDetailsSemanticReviewError, match="duplicate semantic review"):
        build_reviewed_match_details_semantic_review(
            structure=structure,
            structure_bytes=structure_bytes,
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            decisions=(_approved(), _approved()),
            reviewed_at=REVIEWED_AT,
            reviewer_reference="reviewer",
        )

    before_observation = datetime.datetime(2026, 8, 10, 9, 59, tzinfo=UTC)
    with pytest.raises(FotMobReviewedMatchDetailsSemanticReviewError, match="predate exact evidence"):
        build_reviewed_match_details_semantic_review(
            structure=structure,
            structure_bytes=structure_bytes,
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            decisions=(_approved(),),
            reviewed_at=before_observation,
            reviewer_reference="reviewer",
        )

    with pytest.raises(FotMobReviewedMatchDetailsSemanticReviewError, match="datetime.timezone.utc"):
        build_reviewed_match_details_semantic_review(
            structure=structure,
            structure_bytes=structure_bytes,
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            decisions=(_approved(),),
            reviewed_at=REVIEWED_AT.replace(tzinfo=None),
            reviewer_reference="reviewer",
        )


def test_canonicalization_rejects_forced_safety_mutation() -> None:
    review, *_ = _build()
    unsafe = dict(review.safety)
    unsafe["intelligence_fact_authorized"] = True
    object.__setattr__(review, "safety", unsafe)
    with pytest.raises(FotMobReviewedMatchDetailsSemanticReviewError):
        canonical_reviewed_match_details_semantic_review_bytes(review)


def test_review_does_not_require_or_imply_pre_kickoff_human_review() -> None:
    raw = b'{"general":{"homeTeam":{"id":1}},"noise":"x"}'
    _, evidence, evidence_receipt, manifest, structure, structure_bytes = _build(raw)
    after_kickoff = datetime.datetime(2026, 8, 15, 13, 0, tzinfo=UTC)
    review = build_reviewed_match_details_semantic_review(
        structure=structure,
        structure_bytes=structure_bytes,
        evidence=evidence,
        evidence_receipt_bytes=evidence_receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
        decisions=(_approved(),),
        reviewed_at=after_kickoff,
        reviewer_reference="historical-review",
    )
    assert review.reviewed_at == after_kickoff
    assert review.evidence_observed_at < review.kickoff
