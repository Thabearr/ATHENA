from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from tests.support.module_loader import load_test_module

from domain.fixture_intelligence import IntelligenceCategory, IntelligenceFactStatus
from domain.fotmob_reviewed_match_details_field_evidence_qualification import (
    QUALIFICATION_SCOPE,
    FieldEvidenceQualificationDisposition,
    FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
    MatchDetailsFieldEvidenceReviewDecision,
    ReviewedMatchDetailsFieldEvidenceQualification,
    build_reviewed_match_details_field_evidence_qualification,
    canonical_reviewed_match_details_field_evidence_qualification_bytes,
    revalidate_reviewed_match_details_field_evidence_qualification,
    sha256_reviewed_match_details_field_evidence_qualification,
)
from domain.fotmob_reviewed_match_details_structure import JsonValueKind
from domain.fotmob_reviewed_match_details_unverified_facts import (
    canonical_reviewed_match_details_unverified_fact_bundle_bytes,
)


def _pr57_helper():
    return load_test_module("test_fotmob_reviewed_match_details_unverified_facts")


def _approved(pointer: str, kind: JsonValueKind, category: IntelligenceCategory, field: str):
    return _pr57_helper()._approved(pointer, kind, category, field)


def _fact_chain(raw: bytes, decisions):
    helper = _pr57_helper()
    fact_bundle, _, _, chain = helper._fact_bundle(raw, tuple(decisions))
    fact_bytes = canonical_reviewed_match_details_unverified_fact_bundle_bytes(fact_bundle)
    return fact_bundle, fact_bytes, chain


def _review_decisions(
    fact_bundle,
    dispositions: dict[str, FieldEvidenceQualificationDisposition] | None = None,
):
    dispositions = dispositions or {}
    items = []
    for fact in fact_bundle.facts:
        items.append(
            MatchDetailsFieldEvidenceReviewDecision(
                category=fact.category,
                field=fact.field,
                source_reference=fact.source_reference,
                disposition=dispositions.get(
                    fact.field,
                    FieldEvidenceQualificationDisposition.QUALIFIED,
                ),
                rationale=f"Explicit exact-observation review for {fact.field}.",
            )
        )
    return tuple(sorted(items, key=lambda item: item.key))


def _qualification_reviewed_at(fact_bundle, semantic_review) -> datetime.datetime:
    start = max(fact_bundle.observed_at, semantic_review.reviewed_at)
    return start + ((fact_bundle.kickoff - start) / 2)


def _build_qualification(raw: bytes, approved_decisions, dispositions=None):
    fact_bundle, fact_bytes, chain = _fact_chain(raw, approved_decisions)
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    qualification = build_reviewed_match_details_field_evidence_qualification(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        review=review,
        review_bytes=review_bytes,
        fact_bundle=fact_bundle,
        fact_bundle_bytes=fact_bytes,
        decisions=_review_decisions(fact_bundle, dispositions),
        reviewed_at=_qualification_reviewed_at(fact_bundle, review),
        reviewer_reference="ATHENA-PR58-TEST",
    )
    qualification_bytes = canonical_reviewed_match_details_field_evidence_qualification_bytes(
        qualification
    )
    return qualification, qualification_bytes, fact_bundle, fact_bytes, chain


def _two_approved():
    return (
        _approved(
            "/alpha/label",
            JsonValueKind.STRING,
            IntelligenceCategory.FIXTURE_CONTEXT,
            "synthetic_label",
        ),
        _approved(
            "/alpha/value",
            JsonValueKind.INTEGER,
            IntelligenceCategory.MATCH_CONTEXT,
            "synthetic_metric",
        ),
    )


def _one_approved():
    return (
        _approved(
            "/alpha/value",
            JsonValueKind.INTEGER,
            IntelligenceCategory.MATCH_CONTEXT,
            "synthetic_metric",
        ),
    )


def test_exact_observation_review_records_qualified_and_rejected_without_status_promotion() -> None:
    raw = b'{"alpha":{"label":"ok","value":100}}'
    qualification, _, fact_bundle, _, chain = _build_qualification(
        raw,
        _two_approved(),
        {"synthetic_label": FieldEvidenceQualificationDisposition.REJECTED},
    )
    semantic_review = chain[-2]

    assert type(qualification) is ReviewedMatchDetailsFieldEvidenceQualification
    assert qualification.qualification_scope == QUALIFICATION_SCOPE
    assert qualification.qualified_count == 1
    assert qualification.rejected_count == 1
    assert len(qualification.decisions) == len(fact_bundle.facts) == 2
    assert qualification.fixture_identifier == fact_bundle.fixture_identifier
    assert qualification.source_match_id == fact_bundle.source_match_id
    assert qualification.kickoff == fact_bundle.kickoff
    assert qualification.observed_at == fact_bundle.observed_at
    assert qualification.semantic_reviewed_at == semantic_review.reviewed_at
    assert qualification.raw_sha256 == fact_bundle.raw_sha256
    assert qualification.evidence_file_path == fact_bundle.evidence_file_path
    assert qualification.semantic_reviewed_at <= qualification.reviewed_at < qualification.kickoff
    assert all(fact.status is IntelligenceFactStatus.UNVERIFIED for fact in fact_bundle.facts)
    assert all(value is False for value in qualification.safety.values())

    payload = qualification.to_dict()
    assert "facts" not in payload
    assert "source_capability" not in payload
    assert payload["qualification_scope"] == "EXACT_OBSERVATION_ONLY"
    assert payload["safety"]["source_wide_qualification_authorized"] is False
    assert payload["safety"]["supported_status_authorized"] is False


def test_review_decisions_must_cover_every_and_only_exact_pr57_fact() -> None:
    raw = b'{"alpha":{"label":"ok","value":100}}'
    fact_bundle, fact_bytes, chain = _fact_chain(raw, _two_approved())
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    complete = _review_decisions(fact_bundle)
    reviewed_at = _qualification_reviewed_at(fact_bundle, review)

    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="every and only exact PR #57 fact",
    ):
        build_reviewed_match_details_field_evidence_qualification(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bytes,
            decisions=complete[:-1],
            reviewed_at=reviewed_at,
            reviewer_reference="ATHENA-PR58-TEST",
        )

    first = complete[0]
    extra = MatchDetailsFieldEvidenceReviewDecision(
        category=IntelligenceCategory.PERFORMANCE,
        field="invented_metric",
        source_reference=first.source_reference,
        disposition=FieldEvidenceQualificationDisposition.REJECTED,
        rationale="Explicitly rejected invented target.",
    )
    supplied = tuple(sorted(complete + (extra,), key=lambda item: item.key))
    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="every and only exact PR #57 fact",
    ):
        build_reviewed_match_details_field_evidence_qualification(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bytes,
            decisions=supplied,
            reviewed_at=reviewed_at,
            reviewer_reference="ATHENA-PR58-TEST",
        )


def test_review_decisions_must_be_sorted_unique_and_explicit() -> None:
    raw = b'{"alpha":{"label":"ok","value":100}}'
    fact_bundle, fact_bytes, chain = _fact_chain(raw, _two_approved())
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    complete = _review_decisions(fact_bundle)
    reviewed_at = _qualification_reviewed_at(fact_bundle, review)

    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="deterministically sorted",
    ):
        build_reviewed_match_details_field_evidence_qualification(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bytes,
            decisions=tuple(reversed(complete)),
            reviewed_at=reviewed_at,
            reviewer_reference="ATHENA-PR58-TEST",
        )

    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="unique exact facts",
    ):
        build_reviewed_match_details_field_evidence_qualification(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bytes,
            decisions=tuple(sorted((complete[0], complete[0]), key=lambda item: item.key)),
            reviewed_at=reviewed_at,
            reviewer_reference="ATHENA-PR58-TEST",
        )


def test_qualification_requires_exact_pr57_bytes_and_full_chain_revalidation() -> None:
    raw = b'{"alpha":{"value":100}}'
    fact_bundle, fact_bytes, chain = _fact_chain(raw, _one_approved())
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain

    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="full-chain revalidation",
    ):
        build_reviewed_match_details_field_evidence_qualification(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bytes + b"\n",
            decisions=_review_decisions(fact_bundle),
            reviewed_at=_qualification_reviewed_at(fact_bundle, review),
            reviewer_reference="ATHENA-PR58-TEST",
        )


def test_qualification_review_must_follow_semantic_review_and_remain_pre_kickoff() -> None:
    raw = b'{"alpha":{"value":100}}'
    fact_bundle, fact_bytes, chain = _fact_chain(raw, _one_approved())
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain
    decisions = _review_decisions(fact_bundle)

    invalid_times = (
        review.reviewed_at - datetime.timedelta(microseconds=1),
        fact_bundle.kickoff,
        fact_bundle.kickoff + datetime.timedelta(microseconds=1),
    )
    for invalid in invalid_times:
        with pytest.raises(
            FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
            match="reviewed_at",
        ):
            build_reviewed_match_details_field_evidence_qualification(
                evidence=evidence,
                evidence_receipt_bytes=receipt,
                manifest_bytes=manifest,
                raw_bytes=raw,
                assessment=assessment,
                assessment_bytes=assessment_bytes,
                review=review,
                review_bytes=review_bytes,
                fact_bundle=fact_bundle,
                fact_bundle_bytes=fact_bytes,
                decisions=decisions,
                reviewed_at=invalid,
                reviewer_reference="ATHENA-PR58-TEST",
            )


def test_detached_evidence_path_and_source_fixture_are_self_validating() -> None:
    raw = b'{"alpha":{"value":100}}'
    qualification, _, _, _, _ = _build_qualification(raw, _one_approved())

    object.__setattr__(qualification, "evidence_file_path", "forged/response.json")
    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="durable capture identity",
    ):
        canonical_reviewed_match_details_field_evidence_qualification_bytes(qualification)

    qualification, _, _, _, _ = _build_qualification(raw, _one_approved())
    object.__setattr__(
        qualification.decisions[0],
        "source_reference",
        "/api/matchDetails?matchId=999999#/alpha/value",
    )
    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="source fixture",
    ):
        canonical_reviewed_match_details_field_evidence_qualification_bytes(qualification)


def test_full_chain_revalidation_rejects_mutated_recorded_fact_hash() -> None:
    raw = b'{"alpha":{"value":100}}'
    qualification, _, fact_bundle, fact_bytes, chain = _build_qualification(
        raw,
        _one_approved(),
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain

    object.__setattr__(qualification.decisions[0], "fact_sha256", "0" * 64)
    forged_bytes = canonical_reviewed_match_details_field_evidence_qualification_bytes(
        qualification
    )
    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="full-chain",
    ):
        revalidate_reviewed_match_details_field_evidence_qualification(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bytes,
            qualification=qualification,
            qualification_bytes=forged_bytes,
        )


def test_qualification_cannot_be_reused_for_different_exact_raw_observation() -> None:
    raw_a = b'{"alpha":{"value":100}}'
    raw_b = b'{"alpha":{"value":101}}'
    qualification, qualification_bytes, _, _, _ = _build_qualification(
        raw_a,
        _one_approved(),
    )
    other_bundle, other_bytes, other_chain = _fact_chain(raw_b, _one_approved())
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = other_chain

    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="full-chain",
    ):
        revalidate_reviewed_match_details_field_evidence_qualification(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw_b,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=other_bundle,
            fact_bundle_bytes=other_bytes,
            qualification=qualification,
            qualification_bytes=qualification_bytes,
        )


def test_exact_qualification_bytes_are_required() -> None:
    raw = b'{"alpha":{"value":100}}'
    qualification, qualification_bytes, fact_bundle, fact_bytes, chain = _build_qualification(
        raw,
        _one_approved(),
    )
    evidence, receipt, manifest, assessment, assessment_bytes, review, review_bytes = chain

    rebuilt = revalidate_reviewed_match_details_field_evidence_qualification(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        review=review,
        review_bytes=review_bytes,
        fact_bundle=fact_bundle,
        fact_bundle_bytes=fact_bytes,
        qualification=qualification,
        qualification_bytes=qualification_bytes,
    )
    assert rebuilt.to_dict() == qualification.to_dict()

    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="exact canonical PR #58 bytes",
    ):
        revalidate_reviewed_match_details_field_evidence_qualification(
            evidence=evidence,
            evidence_receipt_bytes=receipt,
            manifest_bytes=manifest,
            raw_bytes=raw,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bytes,
            qualification=qualification,
            qualification_bytes=qualification_bytes + b"\n",
        )


def test_canonical_bytes_are_deterministic_and_safety_cannot_be_upgraded() -> None:
    raw = b'{"alpha":{"value":100}}'
    qualification, qualification_bytes, _, _, _ = _build_qualification(
        raw,
        _one_approved(),
    )

    assert qualification_bytes.endswith(b"\n")
    assert canonical_reviewed_match_details_field_evidence_qualification_bytes(
        qualification
    ) == qualification_bytes
    assert len(sha256_reviewed_match_details_field_evidence_qualification(qualification)) == 64

    unsafe = dict(qualification.safety)
    unsafe["supported_status_authorized"] = True
    object.__setattr__(qualification, "safety", unsafe)
    with pytest.raises(
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        match="safety",
    ):
        canonical_reviewed_match_details_field_evidence_qualification_bytes(qualification)


def test_module_has_no_source_wide_registry_snapshot_or_network_side_effects() -> None:
    module_path = (
        Path(__file__).parents[1]
        / "domain"
        / "fotmob_reviewed_match_details_field_evidence_qualification.py"
    )
    source = module_path.read_text(encoding="utf-8")

    forbidden = (
        "domain.source_capabilities",
        "SOURCE_CAPABILITY_REGISTRY",
        "build_snapshot",
        "build_model_feature_snapshot",
        "requests.",
        "httpx.",
        "aiohttp.",
        "urllib.request",
        "socket.",
    )
    for token in forbidden:
        assert token not in source
