from __future__ import annotations

import dataclasses
import datetime
import importlib.util
from pathlib import Path

import pytest

from domain.fixture_intelligence import IntelligenceCategory
from domain.fotmob_reviewed_match_details_field_review import (
    FieldReviewDisposition,
    FotMobReviewedMatchDetailsFieldReviewError,
    MatchDetailsFieldReviewDecision,
    build_reviewed_match_details_field_semantics,
    canonical_reviewed_match_details_field_semantics_bytes,
    sha256_reviewed_match_details_field_semantics,
)
from domain.fotmob_reviewed_match_details_structure import (
    JsonValueKind,
    assess_reviewed_match_details_structure,
    canonical_reviewed_match_details_structure_bytes,
)

UTC = datetime.timezone.utc
REVIEWED_AT = datetime.datetime(2026, 8, 10, 10, 1, tzinfo=UTC)


def _chain(raw: bytes):
    helper_path = Path(__file__).with_name("test_fotmob_reviewed_match_details_structure.py")
    spec = importlib.util.spec_from_file_location("_athena_pr53_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #53 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    evidence, receipt, manifest = module._pr52(raw)
    assessment = assess_reviewed_match_details_structure(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
    )
    assessment_bytes = canonical_reviewed_match_details_structure_bytes(assessment)
    return evidence, receipt, manifest, assessment, assessment_bytes


def _approved(pointer="/alpha/value", kind=JsonValueKind.INTEGER):
    return MatchDetailsFieldReviewDecision(
        json_pointer=pointer,
        expected_kind=kind,
        disposition=FieldReviewDisposition.APPROVED,
        category=IntelligenceCategory.MATCH_CONTEXT,
        field="synthetic_scalar",
        notes="synthetic reviewer-approved mapping for contract test only",
    )


def _build(raw: bytes, decisions=None):
    evidence, receipt, manifest, assessment, assessment_bytes = _chain(raw)
    review = build_reviewed_match_details_field_semantics(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        decisions=decisions or (_approved(),),
        reviewed_at=REVIEWED_AT,
        reviewer_reference="SYNTHETIC-REVIEW-001",
    )
    return review, (evidence, receipt, manifest, assessment, assessment_bytes)


def test_explicit_approved_scalar_mapping_is_deterministic_but_authorizes_no_fact() -> None:
    raw = b'{"alpha":{"value":100}}'
    review, _ = _build(raw)
    assert len(review.decisions) == 1
    decision = review.decisions[0]
    assert decision.disposition is FieldReviewDisposition.APPROVED
    assert decision.category is IntelligenceCategory.MATCH_CONTEXT
    assert decision.field == "synthetic_scalar"
    assert all(value is False for value in review.safety.values())
    canonical = canonical_reviewed_match_details_field_semantics_bytes(review)
    assert canonical.endswith(b"\n")
    assert len(sha256_reviewed_match_details_field_semantics(review)) == 64


def test_rejected_path_carries_no_semantic_mapping() -> None:
    raw = b'{"records":[{"token":"x"}]}'
    decision = MatchDetailsFieldReviewDecision(
        json_pointer="/records/*/token",
        expected_kind=JsonValueKind.STRING,
        disposition=FieldReviewDisposition.REJECTED,
        category=None,
        field=None,
        notes="array semantics intentionally deferred",
    )
    review, _ = _build(raw, (decision,))
    assert review.decisions[0].category is None
    assert review.decisions[0].field is None


def test_approved_array_wildcards_objects_nulls_and_ambiguous_kinds_fail_closed() -> None:
    with pytest.raises(FotMobReviewedMatchDetailsFieldReviewError, match="array wildcard"):
        _approved("/records/*/token", JsonValueKind.STRING)
    with pytest.raises(FotMobReviewedMatchDetailsFieldReviewError, match="non-null scalar"):
        _approved("/alpha", JsonValueKind.OBJECT)
    with pytest.raises(FotMobReviewedMatchDetailsFieldReviewError, match="non-null scalar"):
        _approved("/nullable", JsonValueKind.NULL)

    raw = b'{"records":[{"value":1},{"value":2.5}]}'
    evidence, receipt, manifest, assessment, assessment_bytes = _chain(raw)
    decision = MatchDetailsFieldReviewDecision(
        json_pointer="/records/*/value",
        expected_kind=JsonValueKind.INTEGER,
        disposition=FieldReviewDisposition.REJECTED,
        category=None,
        field=None,
        notes="mixed kinds observed",
    )
    review = build_reviewed_match_details_field_semantics(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        decisions=(decision,),
        reviewed_at=REVIEWED_AT,
        reviewer_reference="SYNTHETIC-REVIEW-002",
    )
    assert review.decisions[0].disposition is FieldReviewDisposition.REJECTED


def test_exact_pr53_assessment_object_and_bytes_are_required() -> None:
    raw = b'{"alpha":{"value":100}}'
    evidence, receipt, manifest, assessment, assessment_bytes = _chain(raw)
    with pytest.raises(FotMobReviewedMatchDetailsFieldReviewError, match="exact canonical PR #53"):
        build_reviewed_match_details_field_semantics(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes + b"\n",
            decisions=(_approved(),),
            reviewed_at=REVIEWED_AT,
            reviewer_reference="SYNTHETIC-REVIEW-003",
        )
    object.__setattr__(assessment, "raw_sha256", "f" * 64)
    with pytest.raises(FotMobReviewedMatchDetailsFieldReviewError):
        build_reviewed_match_details_field_semantics(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            decisions=(_approved(),),
            reviewed_at=REVIEWED_AT,
            reviewer_reference="SYNTHETIC-REVIEW-004",
        )


def test_decision_path_and_kind_must_be_observed_exactly() -> None:
    raw = b'{"alpha":{"value":100}}'
    evidence, receipt, manifest, assessment, assessment_bytes = _chain(raw)
    for decision, pattern in (
        (_approved("/alpha/missing", JsonValueKind.INTEGER), "not observed"),
        (_approved("/alpha/value", JsonValueKind.STRING), "expected_kind"),
    ):
        with pytest.raises(FotMobReviewedMatchDetailsFieldReviewError, match=pattern):
            build_reviewed_match_details_field_semantics(
                evidence=evidence,
                evidence_receipt_bytes=receipt,
                manifest_bytes=manifest,
                raw_bytes=raw,
                assessment=assessment,
                assessment_bytes=assessment_bytes,
                decisions=(decision,),
                reviewed_at=REVIEWED_AT,
                reviewer_reference="SYNTHETIC-REVIEW-005",
            )


def test_review_time_must_follow_observation_and_precede_kickoff() -> None:
    raw = b'{"alpha":{"value":100}}'
    evidence, receipt, manifest, assessment, assessment_bytes = _chain(raw)
    for reviewed_at in (
        evidence.observed_at - datetime.timedelta(microseconds=1),
        evidence.kickoff,
    ):
        with pytest.raises(FotMobReviewedMatchDetailsFieldReviewError):
            build_reviewed_match_details_field_semantics(
                evidence=evidence,
                evidence_receipt_bytes=receipt,
                manifest_bytes=manifest,
                raw_bytes=raw,
                assessment=assessment,
                assessment_bytes=assessment_bytes,
                decisions=(_approved(),),
                reviewed_at=reviewed_at,
                reviewer_reference="SYNTHETIC-REVIEW-006",
            )


def test_duplicate_paths_and_duplicate_semantic_targets_fail_closed() -> None:
    raw = b'{"alpha":{"a":1,"b":2}}'
    d1 = MatchDetailsFieldReviewDecision(
        json_pointer="/alpha/a",
        expected_kind=JsonValueKind.INTEGER,
        disposition=FieldReviewDisposition.APPROVED,
        category=IntelligenceCategory.MATCH_CONTEXT,
        field="synthetic_metric",
        notes="",
    )
    d2 = dataclasses.replace(d1, json_pointer="/alpha/b")
    with pytest.raises(FotMobReviewedMatchDetailsFieldReviewError, match="targets must be unique"):
        _build(raw, (d1, d2))
    with pytest.raises(FotMobReviewedMatchDetailsFieldReviewError, match="unique json_pointer"):
        _build(raw, (d1, d1))
