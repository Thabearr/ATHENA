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
from domain.fotmob_reviewed_match_details_fact_candidates import (
    CAPTURE_ROOT,
    SOURCE_PROVIDER,
    FotMobReviewedMatchDetailsFactCandidateError,
    build_reviewed_match_details_fact_candidates,
    canonical_reviewed_match_details_fact_candidates_bytes,
    sha256_reviewed_match_details_fact_candidates,
)
from domain.fotmob_reviewed_match_details_field_review import (
    FieldReviewDisposition,
    MatchDetailsFieldReviewDecision,
    build_reviewed_match_details_field_semantics,
    canonical_reviewed_match_details_field_semantics_bytes,
)
from domain.fotmob_reviewed_match_details_structure import JsonValueKind

UTC = datetime.timezone.utc
REVIEWED_AT = datetime.datetime(2026, 8, 10, 10, 1, tzinfo=UTC)


def _chain(raw: bytes, decisions: tuple[MatchDetailsFieldReviewDecision, ...]):
    helper_path = Path(__file__).with_name("test_fotmob_reviewed_match_details_field_review.py")
    spec = importlib.util.spec_from_file_location("_athena_pr54_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR #54 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    evidence, receipt, manifest, assessment, assessment_bytes = module._chain(raw)
    review = build_reviewed_match_details_field_semantics(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        decisions=decisions,
        reviewed_at=REVIEWED_AT,
        reviewer_reference="SYNTHETIC-REVIEW-PR55",
    )
    review_bytes = canonical_reviewed_match_details_field_semantics_bytes(review)
    return evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes


def _approved(pointer: str, kind: JsonValueKind, field: str):
    return MatchDetailsFieldReviewDecision(
        json_pointer=pointer,
        expected_kind=kind,
        disposition=FieldReviewDisposition.APPROVED,
        category=IntelligenceCategory.MATCH_CONTEXT,
        field=field,
        notes="synthetic mapping only",
    )


def _build(raw: bytes, decisions):
    chain = _chain(raw, decisions)
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    bundle = build_reviewed_match_details_fact_candidates(
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


def test_approved_scalars_become_only_unverified_fixture_intelligence_facts() -> None:
    raw = b'{"alpha":{"flag":true,"ratio":2.5,"text":"x","value":100}}'
    decisions = (
        _approved("/alpha/value", JsonValueKind.INTEGER, "synthetic_integer"),
        _approved("/alpha/text", JsonValueKind.STRING, "synthetic_string"),
        _approved("/alpha/ratio", JsonValueKind.NUMBER, "synthetic_number"),
        _approved("/alpha/flag", JsonValueKind.BOOLEAN, "synthetic_boolean"),
    )
    bundle, (evidence, *_rest) = _build(raw, decisions)
    assert len(bundle.facts) == 4
    assert {fact.status for fact in bundle.facts} == {IntelligenceFactStatus.UNVERIFIED}
    assert {fact.source_role for fact in bundle.facts} == {SourceRole.PRIMARY_FOOTBALL_CONTEXT}
    assert {fact.source_provider for fact in bundle.facts} == {SOURCE_PROVIDER}
    values = {fact.field: fact.value for fact in bundle.facts}
    assert values == {
        "synthetic_boolean": True,
        "synthetic_integer": 100,
        "synthetic_number": 2.5,
        "synthetic_string": "x",
    }
    expected_identifier = (
        f"{evidence.source_match_id}--"
        f"{evidence.observed_at.strftime('%Y%m%dT%H%M%S%fZ')}--"
        f"{evidence.raw_sha256}"
    )
    expected_path = str(CAPTURE_ROOT / expected_identifier / "response.json")
    assert bundle.evidence_file_path == expected_path
    assert all(fact.evidence_file_path == expected_path for fact in bundle.facts)
    assert all(fact.evidence_sha256 == evidence.raw_sha256 for fact in bundle.facts)
    assert all(value is False for value in bundle.safety.values())
    canonical = canonical_reviewed_match_details_fact_candidates_bytes(bundle)
    assert canonical.endswith(b"\n")
    assert len(sha256_reviewed_match_details_fact_candidates(bundle)) == 64


def test_rejected_decisions_are_not_extracted() -> None:
    raw = b'{"alpha":{"a":1,"b":2}}'
    approved = _approved("/alpha/a", JsonValueKind.INTEGER, "synthetic_a")
    rejected = MatchDetailsFieldReviewDecision(
        json_pointer="/alpha/b",
        expected_kind=JsonValueKind.INTEGER,
        disposition=FieldReviewDisposition.REJECTED,
        category=None,
        field=None,
        notes="not approved",
    )
    bundle, _ = _build(raw, (approved, rejected))
    assert len(bundle.facts) == 1
    assert bundle.facts[0].field == "synthetic_a"


def test_literal_reserved_characters_resolve_exactly_without_aliasing() -> None:
    raw = b'{"a/b~c*":{"value":7}}'
    decision = _approved(
        "/a~1b~0c~2/value",
        JsonValueKind.INTEGER,
        "synthetic_escaped",
    )
    bundle, _ = _build(raw, (decision,))
    assert bundle.facts[0].value == 7
    assert bundle.facts[0].source_reference.endswith("#/a~1b~0c~2/value")


def test_exact_pr54_object_and_exact_review_bytes_are_required() -> None:
    raw = b'{"alpha":{"value":100}}'
    decision = _approved("/alpha/value", JsonValueKind.INTEGER, "synthetic_scalar")
    chain = _chain(raw, (decision,))
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    with pytest.raises(FotMobReviewedMatchDetailsFactCandidateError, match="exact canonical PR #54"):
        build_reviewed_match_details_fact_candidates(
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
    with pytest.raises(FotMobReviewedMatchDetailsFactCandidateError):
        build_reviewed_match_details_fact_candidates(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
        )


def test_all_rejected_review_cannot_create_fact_candidate_bundle() -> None:
    raw = b'{"alpha":{"value":100}}'
    rejected = MatchDetailsFieldReviewDecision(
        json_pointer="/alpha/value",
        expected_kind=JsonValueKind.INTEGER,
        disposition=FieldReviewDisposition.REJECTED,
        category=None,
        field=None,
        notes="not approved",
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = _chain(
        raw, (rejected,)
    )
    with pytest.raises(FotMobReviewedMatchDetailsFactCandidateError, match="at least one explicit"):
        build_reviewed_match_details_fact_candidates(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
        )


def test_runtime_value_kind_cannot_drift_from_reviewed_kind() -> None:
    original = b'{"alpha":{"value":100}}'
    decision = _approved("/alpha/value", JsonValueKind.INTEGER, "synthetic_scalar")
    chain = _chain(original, (decision,))
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    # Any raw-byte change is rejected by the ancestry chain before resolution.
    with pytest.raises(FotMobReviewedMatchDetailsFactCandidateError):
        build_reviewed_match_details_fact_candidates(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=b'{"alpha":{"value":"100"}}',
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
        )


def test_candidate_bundle_rejects_any_attempt_to_upgrade_fact_status() -> None:
    raw = b'{"alpha":{"value":100}}'
    decision = _approved("/alpha/value", JsonValueKind.INTEGER, "synthetic_scalar")
    bundle, _ = _build(raw, (decision,))
    supported = dataclasses.replace(
        bundle.facts[0],
        status=IntelligenceFactStatus.SUPPORTED,
    )
    with pytest.raises(FotMobReviewedMatchDetailsFactCandidateError, match="UNVERIFIED"):
        dataclasses.replace(bundle, facts=(supported,))
