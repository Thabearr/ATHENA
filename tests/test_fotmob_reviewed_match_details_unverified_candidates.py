from __future__ import annotations

import dataclasses
import datetime
import importlib.util
from pathlib import Path

import pytest

from domain.fixture_intelligence import (
    IntelligenceCategory,
    IntelligenceFactStatus,
    SourceRole,
)
from domain.fotmob_reviewed_match_details_field_review import (
    FieldReviewDisposition,
    MatchDetailsFieldReviewDecision,
    build_reviewed_match_details_field_semantics,
    canonical_reviewed_match_details_field_semantics_bytes,
)
from domain.fotmob_reviewed_match_details_structure import (
    JsonValueKind,
    assess_reviewed_match_details_structure,
    canonical_reviewed_match_details_structure_bytes,
)
from domain.fotmob_reviewed_match_details_unverified_candidates import (
    FotMobReviewedMatchDetailsUnverifiedCandidateError,
    SOURCE_PROVIDER,
    build_reviewed_match_details_unverified_candidates,
    canonical_reviewed_match_details_unverified_candidate_bundle_bytes,
    sha256_reviewed_match_details_unverified_candidate_bundle,
)

UTC = datetime.timezone.utc
REVIEWED_AT = datetime.datetime(2026, 8, 10, 10, 1, tzinfo=UTC)


def _pr52(raw: bytes):
    helper_path = Path(__file__).with_name("test_fotmob_reviewed_match_details_structure.py")
    spec = importlib.util.spec_from_file_location("_athena_pr53_candidate_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #53 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._pr52(raw)


def _approved(pointer: str, kind: JsonValueKind, category: IntelligenceCategory, field: str):
    return MatchDetailsFieldReviewDecision(
        json_pointer=pointer,
        expected_kind=kind,
        disposition=FieldReviewDisposition.APPROVED,
        category=category,
        field=field,
        notes="synthetic reviewer-approved mapping for PR #55 contract test only",
    )


def _rejected(pointer: str, kind: JsonValueKind):
    return MatchDetailsFieldReviewDecision(
        json_pointer=pointer,
        expected_kind=kind,
        disposition=FieldReviewDisposition.REJECTED,
        category=None,
        field=None,
        notes="synthetic rejected mapping",
    )


def _chain(raw: bytes, decisions):
    evidence, receipt, manifest = _pr52(raw)
    assessment = assess_reviewed_match_details_structure(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
    )
    assessment_bytes = canonical_reviewed_match_details_structure_bytes(assessment)
    review = build_reviewed_match_details_field_semantics(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        decisions=tuple(decisions),
        reviewed_at=REVIEWED_AT,
        reviewer_reference="SYNTHETIC-PR55-REVIEW",
    )
    review_bytes = canonical_reviewed_match_details_field_semantics_bytes(review)
    return evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes


def _build(raw: bytes, decisions):
    chain = _chain(raw, decisions)
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    bundle = build_reviewed_match_details_unverified_candidates(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        review=review,
        review_bytes=review_bytes,
    )
    return bundle, chain


def test_only_approved_scalars_are_extracted_and_remain_unverified() -> None:
    raw = b'{"alpha":{"label":"ok","value":100},"reject":"ignore"}'
    decisions = (
        _approved(
            "/alpha/value",
            JsonValueKind.INTEGER,
            IntelligenceCategory.MATCH_CONTEXT,
            "synthetic_metric",
        ),
        _approved(
            "/alpha/label",
            JsonValueKind.STRING,
            IntelligenceCategory.FIXTURE_CONTEXT,
            "synthetic_label",
        ),
        _rejected("/reject", JsonValueKind.STRING),
    )
    bundle, _ = _build(raw, decisions)
    assert len(bundle.candidates) == 2
    by_field = {item.field: item for item in bundle.candidates}
    assert by_field["synthetic_metric"].value == 100
    assert by_field["synthetic_metric"].json_kind is JsonValueKind.INTEGER
    assert by_field["synthetic_label"].value == "ok"
    assert all(item.status is IntelligenceFactStatus.UNVERIFIED for item in bundle.candidates)
    assert all(item.source_role is SourceRole.PRIMARY_FOOTBALL_CONTEXT for item in bundle.candidates)
    assert all(item.source_provider == SOURCE_PROVIDER for item in bundle.candidates)
    assert all(item.evidence_sha256 == bundle.raw_sha256 for item in bundle.candidates)
    assert all(value is False for value in bundle.safety.values())
    assert "reject" not in {item.field for item in bundle.candidates}

    canonical = canonical_reviewed_match_details_unverified_candidate_bundle_bytes(bundle)
    assert canonical.endswith(b"\n")
    assert len(sha256_reviewed_match_details_unverified_candidate_bundle(bundle)) == 64


def test_exact_pr54_object_and_canonical_bytes_are_required() -> None:
    raw = b'{"alpha":{"value":100}}'
    decisions = (
        _approved(
            "/alpha/value",
            JsonValueKind.INTEGER,
            IntelligenceCategory.MATCH_CONTEXT,
            "synthetic_metric",
        ),
    )
    _, chain = _build(raw, decisions)
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain

    with pytest.raises(
        FotMobReviewedMatchDetailsUnverifiedCandidateError,
        match="exact canonical PR #54",
    ):
        build_reviewed_match_details_unverified_candidates(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes + b"\n",
        )

    object.__setattr__(review, "raw_sha256", "f" * 64)
    with pytest.raises(FotMobReviewedMatchDetailsUnverifiedCandidateError):
        build_reviewed_match_details_unverified_candidates(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
        )


def test_raw_or_upstream_byte_drift_fails_before_extraction() -> None:
    raw = b'{"alpha":{"value":100}}'
    decisions = (
        _approved(
            "/alpha/value",
            JsonValueKind.INTEGER,
            IntelligenceCategory.MATCH_CONTEXT,
            "synthetic_metric",
        ),
    )
    _, chain = _build(raw, decisions)
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    with pytest.raises(FotMobReviewedMatchDetailsUnverifiedCandidateError, match="PR #54 review"):
        build_reviewed_match_details_unverified_candidates(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw + b" ",
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
        )


def test_literal_star_slash_and_tilde_object_keys_decode_injectively() -> None:
    raw = b'{"a/b":{"~key":{"*":7}}}'
    decision = _approved(
        "/a~1b/~0key/~2",
        JsonValueKind.INTEGER,
        IntelligenceCategory.MATCH_CONTEXT,
        "escaped_key_metric",
    )
    bundle, _ = _build(raw, (decision,))
    candidate = bundle.candidates[0]
    assert candidate.json_pointer == "/a~1b/~0key/~2"
    assert candidate.value == 7


def test_boolean_is_not_treated_as_integer() -> None:
    raw = b'{"flag":true}'
    decision = _approved(
        "/flag",
        JsonValueKind.BOOLEAN,
        IntelligenceCategory.MATCH_CONTEXT,
        "synthetic_flag",
    )
    bundle, _ = _build(raw, (decision,))
    candidate = bundle.candidates[0]
    assert candidate.value is True
    assert candidate.json_kind is JsonValueKind.BOOLEAN


def test_review_with_no_approved_decision_does_not_create_empty_semantic_bundle() -> None:
    raw = b'{"noise":"x"}'
    chain = _chain(raw, (_rejected("/noise", JsonValueKind.STRING),))
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    with pytest.raises(
        FotMobReviewedMatchDetailsUnverifiedCandidateError,
        match="at least one explicitly APPROVED",
    ):
        build_reviewed_match_details_unverified_candidates(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
        )


def test_candidate_cannot_be_mutated_to_supported_or_bet_authorized() -> None:
    raw = b'{"alpha":{"value":100}}'
    decision = _approved(
        "/alpha/value",
        JsonValueKind.INTEGER,
        IntelligenceCategory.MATCH_CONTEXT,
        "synthetic_metric",
    )
    bundle, _ = _build(raw, (decision,))
    candidate = bundle.candidates[0]
    with pytest.raises(FotMobReviewedMatchDetailsUnverifiedCandidateError, match="UNVERIFIED"):
        dataclasses.replace(candidate, status=IntelligenceFactStatus.SUPPORTED)

    unsafe = dict(bundle.safety)
    unsafe["bet_authorized"] = True
    object.__setattr__(bundle, "safety", unsafe)
    with pytest.raises(FotMobReviewedMatchDetailsUnverifiedCandidateError):
        canonical_reviewed_match_details_unverified_candidate_bundle_bytes(bundle)


def test_candidate_source_reference_is_exact_and_source_scoped() -> None:
    raw = b'{"alpha":{"value":100}}'
    decision = _approved(
        "/alpha/value",
        JsonValueKind.INTEGER,
        IntelligenceCategory.MATCH_CONTEXT,
        "synthetic_metric",
    )
    bundle, chain = _build(raw, (decision,))
    evidence = chain[0]
    candidate = bundle.candidates[0]
    assert candidate.source_reference == (
        f"FOTMOB_MATCH_DETAILS:{bundle.source_match_id}:/alpha/value"
    )
    assert candidate.observed_at == evidence.observed_at
    assert bundle.observed_at < bundle.kickoff
